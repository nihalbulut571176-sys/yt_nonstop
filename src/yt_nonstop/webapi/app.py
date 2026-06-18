from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from yt_nonstop.pipeline.project_config import load_project, save_project
from yt_nonstop.pipeline.project_status import build_project_status
from yt_nonstop.webapi.app_state import AppStateStore, AuthSession, lifecycle_status_for
from yt_nonstop.webapi.artifacts import list_artifacts, load_review, load_timeline, preview_file
from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.jobs import JobStore, build_cli_command
from yt_nonstop.webapi.models import (
    ApiErrorEnvelope,
    AssetCollection,
    AudioTextIntakeResponse,
    CommandResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    PipelineAction,
    PipelineActionRequest,
    ActivityEvent,
    CurrentActivity,
    PipelineProgress,
    PipelineState,
    PipelineStageView,
    ProjectOverview,
    ReviewApplyRequest,
    ReviewDecisionRequest,
    ReviewItem,
    ReviewQueue,
    RunDetails,
    RunRequest,
    RunSummary,
    SettingRecord,
    SettingsUpdateRequest,
    ValidateRequest,
    WorkspaceSummary,
    AuthResponse,
    LoginRequest,
)
from yt_nonstop.webapi.project_discovery import discover_projects, get_project


USER_STAGE_GROUPS: tuple[dict, ...] = (
    {"key": "upload", "label": "Upload", "stages": {"upload", "created", "draft"}},
    {"key": "transcribe", "label": "Transcribe", "stages": {"transcription"}},
    {"key": "clean_srt", "label": "Clean SRT", "stages": {"cleanup_transcript_from_source", "ingest_srt"}},
    {
        "key": "scene_plan",
        "label": "Scene Plan",
        "stages": {
            "build_scene_map",
            "allocate_frames",
            "build_narration_beats",
            "author_narration_beats",
            "build_visual_shot_plan",
        },
    },
    {
        "key": "prompts",
        "label": "Prompts",
        "stages": {
            "build_frame_briefs",
            "attach_reference_assets",
            "build_scene_context_pack",
            "generate_fastgen_prompt_drafts",
            "generation_lock",
            "export_montage_map",
            "export_generation_batches",
        },
    },
    {"key": "images", "label": "Images", "stages": {"generate_images", "normalize_images"}},
    {"key": "qc", "label": "QC", "stages": {"image_qc", "final_review", "review"}},
    {"key": "render", "label": "Render", "stages": {"timeline", "render"}},
    {"key": "done", "label": "Done", "stages": {"done", "completed"}},
)

USER_STAGE_PRIMARY_INTERNAL: dict[str, str] = {
    "upload": "transcription",
    "transcribe": "transcription",
    "clean_srt": "cleanup_transcript_from_source",
    "scene_plan": "build_scene_map",
    "prompts": "build_frame_briefs",
    "images": "generate_images",
    "qc": "image_qc",
    "render": "timeline",
    "done": "render",
}


def _stage_group_for(stage_name: str | None) -> dict:
    normalized = str(stage_name or "").strip()
    for group in USER_STAGE_GROUPS:
        if normalized == group["key"] or normalized in group["stages"]:
            return group
    return USER_STAGE_GROUPS[0]


def _group_index(group_key: str | None) -> int:
    for index, group in enumerate(USER_STAGE_GROUPS):
        if group["key"] == group_key:
            return index
    return 0


def _primary_internal_stage(group_key: str | None) -> str:
    return USER_STAGE_PRIMARY_INTERNAL.get(str(group_key or ""), "transcription")


def _command_arg(command: list[str], flag: str) -> str | None:
    try:
        index = command.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(command):
        return None
    return command[index + 1]


def _run_elapsed_sec(run: RunSummary | None) -> float | None:
    if not run or not run.started_at:
        return None
    from datetime import datetime, timezone

    try:
        started = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(run.finished_at.replace("Z", "+00:00")) if run.finished_at else datetime.now(timezone.utc)
    except ValueError:
        return None
    return max(0.0, (finished - started).total_seconds())


def _tail_for_run(jobs: JobStore, run: RunSummary | None, *, tail: int = 12) -> list[str]:
    if not run:
        return []
    try:
        return jobs.read_logs(run.run_id, tail=tail)
    except KeyError:
        return []


def _recent_activity_events(app_state: AppStateStore, jobs: JobStore, runs: list[RunSummary], active_run: RunSummary | None) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    seen: set[str] = set()
    for run in [active_run, *runs[:4]]:
        if not run or run.run_id in seen:
            continue
        seen.add(run.run_id)
        try:
            details = app_state.get_run(run.run_id, log_tail=_tail_for_run(jobs, run, tail=6))
        except KeyError:
            continue
        for event in details.events[-4:]:
            tone = "success" if event.event_type == "completed" else "danger" if event.event_type in {"failed", "rejected"} else "info"
            events.append(ActivityEvent(timestamp=event.created_at, message=event.message, tone=tone))
        for line in details.log_tail[-3:]:
            cleaned = line.strip()
            if cleaned:
                events.append(ActivityEvent(timestamp=None, message=cleaned[:240], tone="neutral"))
    return events[-8:]


def _build_progress_contract(
    *,
    dashboard,
    lifecycle_status: str,
    active_run: RunSummary | None,
    recent_runs: list[RunSummary],
    blocked: list[str],
    jobs: JobStore,
    app_state: AppStateStore,
) -> tuple[list[PipelineStageView], PipelineProgress, CurrentActivity, list[ActivityEvent]]:
    failed = lifecycle_status == "failed" or bool(recent_runs and recent_runs[0].status == "failed" and not active_run)
    blocked_now = lifecycle_status == "blocked" and not active_run and not failed
    internal_stage = dashboard.next_stage or dashboard.current_stage or "upload"
    if active_run:
        internal_stage = dashboard.current_stage or dashboard.next_stage or "transcription"
    if dashboard.completed:
        internal_stage = "done"
    active_group = _stage_group_for(internal_stage)
    active_index = _group_index(active_group["key"])
    stage_views: list[PipelineStageView] = []
    for index, group in enumerate(USER_STAGE_GROUPS):
        status = "pending"
        if dashboard.completed:
            status = "done"
        elif index < active_index:
            status = "done"
        elif index == active_index:
            if active_run:
                status = "running"
            elif failed:
                status = "failed"
            elif blocked_now:
                status = "blocked"
            elif dashboard.warnings and group["key"] in {"images", "qc"}:
                status = "warning"
            else:
                status = "pending"
        progress_current = None
        progress_total = None
        output_label = None
        if group["key"] == "images":
            progress_current = int(dashboard.generated_images_success or dashboard.selected_images_count or 0)
            progress_total = int(dashboard.planned_variants_count or dashboard.generated_images_total or dashboard.selected_images_expected or 0)
            output_label = f"{progress_current} / {progress_total}" if progress_total else None
        elif group["key"] == "scene_plan":
            progress_current = int(dashboard.visual_slots_count or dashboard.narration_beats_count or 0)
            output_label = f"{progress_current} planned shots" if progress_current else None
        elif group["key"] == "render" and dashboard.final_video_path:
            output_label = dashboard.final_video_path
        message = None
        error_message = None
        if status == "running":
            message = "Running now. Green means Studio is actively working."
        elif status == "failed":
            error_message = blocked[0] if blocked else "Latest run failed. Open logs for details."
        elif status == "blocked":
            error_message = blocked[0] if blocked else "Blocked before this step can continue."
        stage_views.append(
            PipelineStageView(
                key=group["key"],
                label=group["label"],
                status=status,
                progress_current=progress_current,
                progress_total=progress_total,
                message=message,
                error_message=error_message,
                output_label=output_label,
            )
        )
    done_count = sum(1 for item in stage_views if item.status == "done")
    partial = 0.5 if active_run else 0
    percent = 100 if dashboard.completed else min(99, int(((done_count + partial) / len(stage_views)) * 100))
    progress = PipelineProgress(
        percent=percent,
        current_stage_key=active_group["key"],
        current_stage_label=str(active_group["label"]),
        elapsed_sec=_run_elapsed_sec(active_run or (recent_runs[0] if recent_runs else None)),
        active_run_id=active_run.run_id if active_run else None,
        is_running=active_run is not None,
        is_failed=failed,
    )
    current_status = "running" if active_run else "failed" if failed else "blocked" if blocked_now else "done" if dashboard.completed else "pending"
    log_tail = _tail_for_run(jobs, active_run or (recent_runs[0] if failed and recent_runs else None), tail=14)
    activity = CurrentActivity(
        title=str(active_group["label"]),
        detail=active_run.action_type if active_run else dashboard.next_command or dashboard.next_stage or "",
        status=current_status,
        run_id=active_run.run_id if active_run else recent_runs[0].run_id if recent_runs else None,
        log_tail=log_tail,
    )
    events = _recent_activity_events(app_state, jobs, recent_runs, active_run)
    return stage_views, progress, activity, events


class ProductApiError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str, details: dict | None = None, retryable: bool = False) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        super().__init__(message)


def _available_pipeline_actions(project, state: PipelineState) -> list[PipelineAction]:
    if not project.project_json_path:
        reason = "This project has no project.json, so CLI-backed pipeline actions are disabled."
        return [
            PipelineAction(key="validate", label="Validate", enabled=False, reason=reason),
            PipelineAction(key="resume", label="Resume", enabled=False, reason=reason),
            PipelineAction(key="retry_failed_only", label="Retry failed only", enabled=False, reason=reason),
            PipelineAction(key="render_dry_run", label="Render dry run", enabled=False, reason=reason),
            PipelineAction(key="run_range", label="Run stage range", enabled=False, reason=reason),
        ]
    active_write = state.active_run is not None
    disabled_reason = f"Active run {state.active_run.run_id} is already running for this project." if active_write else None
    return [
        PipelineAction(key="validate", label="Validate", recommended=not state.blocked and not active_write, enabled=not active_write, reason=disabled_reason),
        PipelineAction(key="resume", label="Resume", recommended=bool(state.next_stage) and not active_write, enabled=not active_write, reason=disabled_reason),
        PipelineAction(
            key="retry_failed_only",
            label="Retry failed only",
            recommended=any(run.status == "failed" for run in state.recent_runs),
            enabled=not active_write,
            reason=disabled_reason,
        ),
        PipelineAction(key="render_dry_run", label="Render dry run", recommended=state.ready_for_render and not active_write, enabled=not active_write, reason=disabled_reason),
        PipelineAction(key="run_range", label="Run stage range", recommended=False, enabled=not active_write, reason=disabled_reason),
    ]


def _failed_stage_from_project(project_json_path: str | None) -> str | None:
    if not project_json_path:
        return None
    try:
        project_payload = load_project(Path(project_json_path))
    except Exception:
        return None
    for key in ("current_stage", "status"):
        value = str(project_payload.get(key) or "").strip()
        if value and value not in {"failed", "running", "completed"}:
            return value
    section_stage_map = {
        "transcription": "transcription",
        "transcript_cleanup": "cleanup_transcript_from_source",
        "scene_plan": "build_scene_map",
        "prompts": "build_frame_briefs",
        "images": "generate_images",
        "qc": "image_qc",
        "render": "render",
    }
    for section_key, stage_name in section_stage_map.items():
        section = project_payload.get(section_key)
        if isinstance(section, dict) and str(section.get("status") or "").lower() in {"failed", "error", "partial", "pending"}:
            return stage_name
    return None


def _stage_from_failed_run(run: RunSummary | None, *, project_json_path: str | None, dashboard) -> tuple[str | None, str | None, str | None, str | None]:
    if not run or run.status != "failed":
        return None, None, None, None
    stage = _command_arg(run.command, "--from")
    if not stage:
        stage = _failed_stage_from_project(project_json_path)
    if not stage:
        stage = dashboard.current_stage or dashboard.next_stage
    group = _stage_group_for(stage)
    internal = stage or _primary_internal_stage(group["key"])
    return group["key"], group["label"], internal, _failed_run_blocker(run)


def _recovery_actions(project, state: PipelineState) -> list[PipelineAction]:
    if not project.project_json_path:
        reason = "Recovery actions need project.json so Studio can run the CLI safely."
        return [
            PipelineAction(key="continue_from_last_success", label="Continue pipeline", enabled=False, reason=reason),
            PipelineAction(key="retry_failed_step", label="Retry failed step", enabled=False, reason=reason),
            PipelineAction(key="retry_failed_only", label="Retry failed images only", enabled=False, reason=reason),
            PipelineAction(key="restart_from_stage", label="Restart from selected stage", enabled=False, reason=reason),
        ]
    if state.active_run:
        reason = f"Active run {state.active_run.run_id} is already running for this project."
        return [
            PipelineAction(key="continue_from_last_success", label="Continue pipeline", enabled=False, reason=reason),
            PipelineAction(key="retry_failed_step", label=f"Retry from {state.failed_stage_label or 'failed step'}", enabled=False, reason=reason),
            PipelineAction(key="retry_failed_only", label="Retry failed images only", enabled=False, reason=reason),
            PipelineAction(key="restart_from_stage", label="Restart from selected stage", enabled=False, reason=reason),
        ]
    failed = bool(state.failed_run_id or state.lifecycle_status == "failed")
    return [
        PipelineAction(key="continue_from_last_success", label="Continue pipeline", recommended=not failed, enabled=True, reason=None),
        PipelineAction(key="retry_failed_step", label=f"Retry from {state.failed_stage_label or 'failed step'}", recommended=failed, enabled=failed, reason=None if failed else "No failed run has been detected."),
        PipelineAction(key="retry_failed_only", label="Retry failed images only", recommended=state.failed_stage_key == "images", enabled=True, reason=None),
        PipelineAction(key="restart_from_stage", label="Restart from selected stage", recommended=False, enabled=True, reason=None),
    ]


def _discover_projects(config: WebConfig, app_state: AppStateStore):
    projects = discover_projects(config)
    app_state.sync_projects(projects)
    return projects


def _failed_run_blocker(run: RunSummary | None) -> str | None:
    if not run or run.status != "failed":
        return None
    message = f"Last run failed during {run.action_type}"
    log_path = Path(run.log_path)
    if log_path.exists():
        lines = [line.strip() for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        interesting = [
            line
            for line in lines[-80:]
            if "error" in line.lower()
            or "runtimeerror" in line.lower()
            or "traceback" in line.lower()
            or "calledprocesserror" in line.lower()
            or "unable to" in line.lower()
        ]
        if interesting:
            message = f"{message}: {interesting[-1][:360]}"
    return message


def _build_pipeline_state(project, jobs: JobStore, app_state: AppStateStore) -> PipelineState:
    active_run = jobs.active_job_for_project(project.id)
    recent_runs = app_state.list_runs(project_id=project.id, limit=10)
    if not project.project_json_path:
        blocked_reason = "Project has limited support in the studio because no project.json was discovered."
        limited_stages = [
            PipelineStageView(
                key=group["key"],
                label=group["label"],
                status="blocked" if group["key"] == "upload" else "pending",
                error_message=blocked_reason if group["key"] == "upload" else None,
            )
            for group in USER_STAGE_GROUPS
        ]
        limited_progress = PipelineProgress(
            percent=0,
            current_stage_key="upload",
            current_stage_label="Upload",
            is_running=False,
            is_failed=False,
        )
        limited_activity = CurrentActivity(
            title="Limited project support",
            detail=blocked_reason,
            status="blocked",
        )
        lifecycle_status = lifecycle_status_for(
            support=project.support,
            blocked=[blocked_reason],
            ready_for_render=False,
            ready_for_human_review=False,
            completed=False,
            active_run=active_run,
            next_stage=project.next_stage,
        )
        state = PipelineState(
            project_id=project.id,
            project_name=project.name,
            support=project.support,
            lifecycle_status=lifecycle_status,
            current_stage=project.current_stage,
            next_stage=project.next_stage,
            next_command=project.next_command,
            blocked=[blocked_reason],
            warnings=[],
            info=["Artifact browsing remains available.", "CLI-backed write actions are disabled for limited-support projects."],
            blocked_count=1,
            warning_count=0,
            active_run=active_run,
            blocked_by_active_run=active_run is not None,
            recent_runs=recent_runs,
            stage_groups=limited_stages,
            progress=limited_progress,
            current_activity=limited_activity,
            recent_events=[ActivityEvent(message=blocked_reason, tone="warning")],
        )
        state.available_actions = _available_pipeline_actions(project, state)
        state.recovery_actions = _recovery_actions(project, state)
        return state

    dashboard = build_project_status(Path(project.project_json_path))
    latest_failed_run = next((run for run in recent_runs if run.status == "failed"), None) if not active_run else None
    failed_stage_key, failed_stage_label, resume_from_stage, failed_error_summary = _stage_from_failed_run(
        latest_failed_run,
        project_json_path=project.project_json_path,
        dashboard=dashboard,
    )
    failed_blocker = failed_error_summary
    blocked = ([failed_blocker] if failed_blocker else []) + list(dashboard.blocked)
    warnings = list(dashboard.warnings)
    lifecycle_status = lifecycle_status_for(
        support=project.support,
        blocked=blocked,
        ready_for_render=dashboard.ready_for_render,
        ready_for_human_review=dashboard.ready_for_human_review,
        completed=dashboard.completed,
        active_run=active_run,
        next_stage=dashboard.next_stage,
    )
    if failed_blocker and not active_run:
        lifecycle_status = "failed"
    app_state.update_project_snapshot(
        project_id=project.id,
        lifecycle_status=lifecycle_status,
        next_command=dashboard.next_command,
        dashboard=dashboard.to_dict(),
        blocked_count=len(blocked),
        warning_count=len(warnings),
        available_outputs=project.available_outputs,
    )
    state = PipelineState(
        project_id=project.id,
        project_name=project.name,
        support=project.support,
        lifecycle_status=lifecycle_status,
        current_stage=dashboard.current_stage,
        next_stage=dashboard.next_stage,
        next_command=dashboard.next_command,
        blocked=blocked,
        warnings=warnings,
        info=dashboard.info,
        blocked_count=len(blocked),
        warning_count=len(warnings),
        ready_for_generation=dashboard.ready_for_generation,
        ready_for_qc=dashboard.ready_for_qc,
        ready_for_render=dashboard.ready_for_render,
        ready_for_human_review=dashboard.ready_for_human_review,
        completed=dashboard.completed,
        active_run=active_run,
        blocked_by_active_run=active_run is not None,
        recent_runs=recent_runs,
        failed_stage_key=failed_stage_key,
        failed_stage_label=failed_stage_label,
        failed_run_id=latest_failed_run.run_id if latest_failed_run else None,
        failed_error_summary=failed_error_summary,
        resume_from_stage=resume_from_stage or dashboard.next_stage or dashboard.current_stage,
        resume_to_stage="render",
    )
    stage_groups, progress, activity, recent_events = _build_progress_contract(
        dashboard=dashboard,
        lifecycle_status=lifecycle_status,
        active_run=active_run,
        recent_runs=recent_runs,
        blocked=blocked,
        jobs=jobs,
        app_state=app_state,
    )
    state.stage_groups = stage_groups
    state.progress = progress
    state.current_activity = activity
    state.recent_events = recent_events
    state.available_actions = _available_pipeline_actions(project, state)
    state.recovery_actions = _recovery_actions(project, state)
    return state


def _pipeline_action_command(project_json_path: str, request: PipelineActionRequest, state: PipelineState | None = None) -> list[str]:
    recovery_from_stage = request.from_stage or (state.resume_from_stage if state else None)
    if request.action == "validate":
        return build_cli_command(project_json_path=project_json_path, action="validate", stage="all")
    if request.action in {"resume", "continue_from_last_success"}:
        return build_cli_command(
            project_json_path=project_json_path,
            action="run",
            to_stage=request.to_stage or "render",
            profile=request.profile,
            limit_frames=request.limit_frames,
            real_generation=request.real_generation,
            concurrency=request.concurrency,
            resume=True,
            dry_run=request.dry_run,
        )
    if request.action == "retry_failed_step":
        return build_cli_command(
            project_json_path=project_json_path,
            action="run",
            from_stage=recovery_from_stage,
            to_stage=request.to_stage or "render",
            profile=request.profile,
            limit_frames=request.limit_frames,
            real_generation=request.real_generation,
            concurrency=request.concurrency,
            resume=True,
            dry_run=request.dry_run,
        )
    if request.action == "retry_failed_only":
        return build_cli_command(
            project_json_path=project_json_path,
            action="run",
            to_stage=request.to_stage or "render",
            profile=request.profile,
            limit_frames=request.limit_frames,
            real_generation=request.real_generation,
            concurrency=request.concurrency,
            retry_failed_only=True,
            dry_run=request.dry_run,
        )
    if request.action == "render_dry_run":
        return build_cli_command(
            project_json_path=project_json_path,
            action="run",
            from_stage=request.from_stage or "timeline",
            to_stage=request.to_stage or "render",
            render_dry_run=True,
            dry_run=request.dry_run,
        )
    if request.action == "restart_from_stage":
        return build_cli_command(
            project_json_path=project_json_path,
            action="run",
            from_stage=recovery_from_stage,
            to_stage=request.to_stage or "render",
            profile=request.profile,
            limit_frames=request.limit_frames,
            real_generation=request.real_generation,
            concurrency=request.concurrency,
            resume=True,
            dry_run=request.dry_run,
        )
    return build_cli_command(
        project_json_path=project_json_path,
        action="run",
        from_stage=request.from_stage,
        to_stage=request.to_stage or "render",
        profile=request.profile,
        limit_frames=request.limit_frames,
        real_generation=request.real_generation,
        concurrency=request.concurrency,
        dry_run=request.dry_run,
    )


def _session_from_request(app: FastAPI, authorization: str | None, token: str | None) -> AuthSession:
    raw_token = token
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization.split(" ", 1)[1].strip()
    if not raw_token:
        raise ProductApiError(status_code=401, code="auth_error", message="Authentication required")
    session = app.state.app_state.get_session(raw_token)
    if not session:
        raise ProductApiError(status_code=401, code="auth_error", message="Session expired or invalid")
    return session


def _slugify_project_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_").lower()
    return normalized or "project"


def _normalize_time_range(start_sec: float | None, end_sec: float | None) -> dict[str, float | bool]:
    if start_sec is None and end_sec is None:
        return {"enabled": False}
    if start_sec is None or end_sec is None:
        raise ProductApiError(status_code=400, code="validation_error", message="Both start and end time are required for a custom range", details={"start_sec": start_sec, "end_sec": end_sec})
    start = max(0.0, float(start_sec))
    end = float(end_sec)
    if end <= start:
        raise ProductApiError(status_code=400, code="validation_error", message="End time must be greater than start time", details={"start_sec": start, "end_sec": end})
    return {"enabled": True, "start_sec": round(start, 3), "end_sec": round(end, 3), "duration_sec": round(end - start, 3)}


def _trim_audio_for_time_range(source_audio: Path, intake_dir: Path, time_range: dict[str, float | bool]) -> Path:
    if not time_range.get("enabled"):
        return source_audio
    if shutil.which("ffmpeg") is None:
        raise ProductApiError(status_code=500, code="system_error", message="ffmpeg is required for custom timing range audio trimming", retryable=False)
    output_path = intake_dir / "source_audio_range.mp3"
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{float(time_range['start_sec']):.3f}",
        "-t",
        f"{float(time_range['duration_sec']):.3f}",
        "-i",
        str(source_audio),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not output_path.exists():
        raise ProductApiError(
            status_code=500,
            code="system_error",
            message="Could not trim source audio for the selected timing range",
            details={"stderr": completed.stderr[-2000:]},
            retryable=True,
        )
    time_range["audio_pretrimmed"] = True
    time_range["original_audio_path"] = str(source_audio)
    time_range["trimmed_audio_path"] = str(output_path)
    return output_path


def _resolve_required_file(value: str | None, *, label: str, details_key: str) -> Path:
    if not value or not value.strip():
        raise ProductApiError(status_code=400, code="validation_error", message=f"{label} is required", details={details_key: value or ""})
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ProductApiError(status_code=400, code="validation_error", message=f"{label} not found: {path}", details={details_key: str(path)})
    return path


def _resolve_optional_file(value: str | None, *, label: str, details_key: str) -> Path | None:
    if not value or not value.strip():
        return None
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ProductApiError(status_code=400, code="validation_error", message=f"{label} not found: {path}", details={details_key: str(path)})
    return path


def _safe_upload_filename(upload: UploadFile, fallback: str) -> str:
    raw_name = Path(upload.filename or fallback).name
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw_name).strip("._")
    return normalized or fallback


async def _stage_upload(upload: UploadFile, destination_dir: Path, fallback_name: str) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / _safe_upload_filename(upload, fallback_name)
    content = await upload.read()
    if not content:
        raise ProductApiError(
            status_code=400,
            code="validation_error",
            message=f"Uploaded file is empty: {upload.filename or fallback_name}",
            details={"filename": upload.filename or fallback_name},
        )
    destination.write_bytes(content)
    return destination


def _run_bootstrap(config: WebConfig, request: CreateProjectRequest) -> CreateProjectResponse:
    if not request.project_name.strip():
        raise ProductApiError(status_code=400, code="validation_error", message="Project name is required", details={"project_name": request.project_name})
    source_srt = _resolve_required_file(request.source_srt_path, label="Source SRT", details_key="source_srt_path")
    source_audio = _resolve_required_file(request.source_audio_path, label="Source audio", details_key="source_audio_path")
    raw_text = _resolve_required_file(request.raw_text_path, label="Raw text", details_key="raw_text_path")
    setup_notes = _resolve_optional_file(request.setup_notes_path, label="Setup notes", details_key="setup_notes_path")

    slug = _slugify_project_name(request.project_name)
    project_root = (config.workspace_root / slug).resolve(strict=False)
    if not config.project_allowed(project_root):
        raise ProductApiError(status_code=403, code="filesystem_error", message="Project root is outside allowed roots", details={"project_root": str(project_root)})
    if project_root.exists():
        raise ProductApiError(status_code=409, code="project_state_error", message=f"Project folder already exists: {project_root}", details={"project_root": str(project_root)})

    command = [
        sys.executable,
        str(config.repo_root / "scripts" / "bootstrap_real_pilot_project.py"),
        "--project-root",
        str(project_root),
        "--source-srt",
        str(source_srt),
        "--profile",
        request.profile or config.default_profile,
    ]
    if source_audio:
        command.extend(["--source-audio", str(source_audio)])
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(config.repo_root))
    if completed.returncode != 0:
        raise ProductApiError(
            status_code=500,
            code="system_error",
            message=completed.stderr.strip() or completed.stdout.strip() or "Project bootstrap failed",
            retryable=False,
        )

    project_json_path = project_root / "project.json"
    shutil.copy2(raw_text, project_root / "input" / "raw_text.md")
    if setup_notes:
        shutil.copy2(setup_notes, project_root / "input" / "project_setup_notes.md")
    return CreateProjectResponse(
        project_id=slug,
        project_name=request.project_name,
        project_root=str(project_root),
        project_json_path=str(project_json_path),
        support="full",
        next_route=f"/projects/{slug}/overview",
        notes=[
            "Project folder bootstrapped from the repo-native real pilot template.",
            "CLI remains the execution source of truth for all stage runs.",
        ],
    )


async def _run_intake_bootstrap(
    config: WebConfig,
    *,
    project_name: str,
    source_srt: UploadFile,
    source_audio: UploadFile,
    raw_text: UploadFile,
    setup_notes: UploadFile | None,
    profile: str,
) -> CreateProjectResponse:
    if not project_name.strip():
        raise ProductApiError(status_code=400, code="validation_error", message="Project name is required", details={"project_name": project_name})
    slug = _slugify_project_name(project_name)
    intake_dir = config.runtime_dir / "uploads" / f"{slug}-{uuid4().hex[:8]}"
    staged_srt = await _stage_upload(source_srt, intake_dir, "source.srt")
    staged_audio = await _stage_upload(source_audio, intake_dir, "source_audio.mp3")
    staged_raw_text = await _stage_upload(raw_text, intake_dir, "raw_text.md")
    staged_notes = await _stage_upload(setup_notes, intake_dir, "project_setup_notes.md") if setup_notes else None
    return _run_bootstrap(
        config,
        CreateProjectRequest(
            project_name=project_name,
            source_srt_path=str(staged_srt),
            source_audio_path=str(staged_audio),
            raw_text_path=str(staged_raw_text),
            setup_notes_path=str(staged_notes) if staged_notes else None,
            profile=profile,
        ),
    )


def _run_audio_text_bootstrap(
    config: WebConfig,
    *,
    project_name: str,
    source_audio: Path,
    raw_text: Path,
    setup_notes: Path | None,
    profile: str,
    time_range: dict[str, float | bool] | None = None,
) -> CreateProjectResponse:
    if not project_name.strip():
        raise ProductApiError(status_code=400, code="validation_error", message="Project name is required", details={"project_name": project_name})
    slug = _slugify_project_name(project_name)
    project_root = (config.workspace_root / slug).resolve(strict=False)
    if not config.project_allowed(project_root):
        raise ProductApiError(status_code=403, code="filesystem_error", message="Project root is outside allowed roots", details={"project_root": str(project_root)})
    if project_root.exists():
        raise ProductApiError(status_code=409, code="project_state_error", message=f"Project folder already exists: {project_root}", details={"project_root": str(project_root)})

    command = [
        sys.executable,
        str(config.repo_root / "scripts" / "bootstrap_real_pilot_project.py"),
        "--project-root",
        str(project_root),
        "--source-audio",
        str(source_audio),
        "--raw-text",
        str(raw_text),
        "--profile",
        profile or config.default_profile,
    ]
    if setup_notes:
        command.extend(["--setup-notes", str(setup_notes)])
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(config.repo_root))
    if completed.returncode != 0:
        raise ProductApiError(
            status_code=500,
            code="system_error",
            message=completed.stderr.strip() or completed.stdout.strip() or "Audio/text project bootstrap failed",
            retryable=False,
        )

    project_json_path = project_root / "project.json"
    project = load_project(project_json_path)
    project.setdefault("runtime", {})["web_intake_flow"] = {
        "mode": "audio_text",
        "timing_contract": "audio range is pretrimmed before transcription; do not pass start/end again to CLI for pretrimmed audio",
        "semantic_source": "cleanup_transcript_from_source selects the matching source text window from raw_text using Whisper transcript text",
        "render_timing_source": "cleaned.srt -> semantic scene plan -> prompts -> generation -> render",
        "steps": [
            "stage uploads",
            "optional audio range trim",
            "Whisper SRT",
            "source-window cleaned SRT",
            "semantic scene plan",
            "LLM-authored prompts",
            "image generation",
            "timeline render",
        ],
    }
    if time_range and time_range.get("enabled"):
        project.setdefault("runtime", {})["time_range"] = time_range
    save_project(project_json_path, project)
    return CreateProjectResponse(
        project_id=slug,
        project_name=project_name,
        project_root=str(project_root),
        project_json_path=str(project_json_path),
        support="full",
        next_route=f"/projects/{slug}/pipeline",
        notes=[
            "Project folder bootstrapped from uploaded audio and script text.",
            "Transcription starts as the first pipeline stage.",
            "Timing contract: audio range -> Whisper SRT -> source-window cleaned SRT -> semantic scene plan -> prompts -> generation -> render.",
        ],
    )


def _review_queue_for_project(*, project_id: str, project_path: Path, project_json_path: Path | None, app_state: AppStateStore) -> ReviewQueue:
    review_payload = load_review(project_id, project_path, project_json_path)
    timeline_payload = load_timeline(project_id, project_path, project_json_path)
    source = review_payload.source or timeline_payload.source
    raw_rows = review_payload.rows if review_payload.rows else timeline_payload.rows
    items = app_state.sync_review_items(project_id=project_id, source=source or "review", rows=raw_rows)
    decisions = app_state.list_review_decisions(project_id)
    summary = {
        "items": len(items),
        "decisions": len(decisions),
        "pending": 0,
        "approved": 0,
        "warning": 0,
        "manual_review": 0,
        "regenerate": 0,
        "rejected": 0,
        "finalized": 0,
    }
    decisions_by_item = {decision.item_id: decision for decision in decisions}
    for item in items:
        decision = decisions_by_item.get(item.item_id)
        review_state = decision.decision if decision else "pending"
        if review_state in summary:
            summary[review_state] += 1
    return ReviewQueue(project_id=project_id, source=source, items=items, decisions=decisions, summary=summary, raw_rows=raw_rows)


def _command_response(result, accepted_message: str, rejected_message: str) -> CommandResponse:
    return CommandResponse(
        accepted=result.accepted,
        run_id=result.job.run_id,
        state=result.job.status,
        message=accepted_message if result.accepted else (result.reason or rejected_message),
    )


def create_app() -> FastAPI:
    config = WebConfig.from_env()
    app_state = AppStateStore(config)
    jobs = JobStore(config, app_state=app_state)
    app = FastAPI(title="yt_nonstop web studio", version="0.3.0")
    app.state.config = config
    app.state.jobs = jobs
    app.state.app_state = app_state
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ProductApiError)
    async def product_error_handler(_request: Request, exc: ProductApiError):
        return JSONResponse(status_code=exc.status_code, content=ApiErrorEnvelope(code=exc.code, message=exc.message, details=exc.details, retryable=exc.retryable).model_dump())

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        code = "validation_error" if exc.status_code == 400 else "auth_error" if exc.status_code == 401 else "filesystem_error" if exc.status_code in {403, 404} else "project_state_error" if exc.status_code == 409 else "system_error"
        return JSONResponse(status_code=exc.status_code, content=ApiErrorEnvelope(code=code, message=str(exc.detail), retryable=False).model_dump())

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception):
        return JSONResponse(status_code=500, content=ApiErrorEnvelope(code="system_error", message=str(exc), retryable=False).model_dump())

    def require_session(authorization: str | None = Header(default=None), token: str | None = Query(default=None)) -> AuthSession:
        return _session_from_request(app, authorization, token)

    def resolve_project(project_id: str):
        try:
            project = get_project(config, project_id)
        except KeyError:
            raise ProductApiError(status_code=404, code="filesystem_error", message="Project not found", details={"project_id": project_id})
        path = Path(project.path)
        if not config.project_allowed(path):
            raise ProductApiError(status_code=403, code="filesystem_error", message="Project path is outside allowed roots", details={"project_id": project_id})
        app_state.touch_project(project.id)
        return project, path

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def auth_login(request: LoginRequest) -> dict[str, object]:
        session = app_state.authenticate(request.username, request.password)
        if not session:
            raise ProductApiError(status_code=401, code="auth_error", message="Invalid username or password")
        return AuthResponse(user=session.user, session=session.session).model_dump()

    @app.post("/api/auth/logout")
    def auth_logout(current: AuthSession = Depends(require_session)):
        app_state.logout(current.session.token)
        return {"ok": True}

    @app.get("/api/auth/me")
    def auth_me(current: AuthSession = Depends(require_session)):
        return AuthResponse(user=current.user, session=current.session).model_dump()

    @app.get("/api/workspace/summary")
    def workspace_summary(_current: AuthSession = Depends(require_session)):
        projects = _discover_projects(config, app_state)
        return app_state.build_workspace_summary(projects).model_dump()

    @app.get("/api/projects")
    def projects(_current: AuthSession = Depends(require_session)):
        return [item.model_dump() for item in _discover_projects(config, app_state)]

    @app.post("/api/projects")
    def create_project(request: CreateProjectRequest, current: AuthSession = Depends(require_session)):
        payload = _run_bootstrap(config, request)
        app_state.upsert_user_preference(
            key="studio_preferences",
            value={
                "default_profile": request.profile or config.default_profile,
                "default_concurrency": config.default_concurrency,
                "default_real_generation": False,
                "last_bootstrapped_project": payload.project_id,
            },
            user_id=current.user.id,
        )
        app_state.record_audit_event(actor_user_id=current.user.id, event_type="project_created", target_type="project", target_id=payload.project_id, payload=payload.model_dump())
        _discover_projects(config, app_state)
        return payload.model_dump()

    @app.post("/api/projects/bootstrap")
    def project_bootstrap_compat(request: CreateProjectRequest, current: AuthSession = Depends(require_session)):
        return create_project(request, current)

    @app.post("/api/projects/intake")
    async def create_project_intake(
        project_name: str = Form(...),
        profile: str = Form("no_vlm_production"),
        source_srt: UploadFile = File(...),
        source_audio: UploadFile = File(...),
        raw_text: UploadFile = File(...),
        setup_notes: UploadFile | None = File(default=None),
        current: AuthSession = Depends(require_session),
    ):
        payload = await _run_intake_bootstrap(
            config,
            project_name=project_name,
            source_srt=source_srt,
            source_audio=source_audio,
            raw_text=raw_text,
            setup_notes=setup_notes,
            profile=profile,
        )
        app_state.upsert_user_preference(
            key="studio_preferences",
            value={
                "default_profile": profile or config.default_profile,
                "default_concurrency": config.default_concurrency,
                "default_real_generation": False,
                "last_bootstrapped_project": payload.project_id,
                "last_intake_mode": "upload",
            },
            user_id=current.user.id,
        )
        app_state.record_audit_event(actor_user_id=current.user.id, event_type="project_intake_created", target_type="project", target_id=payload.project_id, payload=payload.model_dump())
        _discover_projects(config, app_state)
        return payload.model_dump()

    @app.post("/api/projects/intake/audio-text")
    async def create_project_audio_text_intake(
        project_name: str = Form(...),
        profile: str = Form("no_vlm_production"),
        to_stage: str = Form("render"),
        real_generation: bool = Form(True),
        concurrency: int = Form(4),
        start_sec: float | None = Form(default=None),
        end_sec: float | None = Form(default=None),
        source_audio: UploadFile | None = File(default=None),
        raw_text: UploadFile | None = File(default=None),
        style_notes: UploadFile | None = File(default=None),
        current: AuthSession = Depends(require_session),
    ):
        if concurrency < 1 or concurrency > 50:
            raise ProductApiError(status_code=400, code="validation_error", message="Concurrency must be between 1 and 50", details={"concurrency": concurrency})
        if source_audio is None:
            raise ProductApiError(status_code=400, code="validation_error", message="Source audio file is required", details={"field": "source_audio"})
        if raw_text is None:
            raise ProductApiError(status_code=400, code="validation_error", message="Raw script text file is required", details={"field": "raw_text"})
        time_range = _normalize_time_range(start_sec, end_sec)
        slug = _slugify_project_name(project_name)
        intake_dir = config.runtime_dir / "uploads" / f"{slug}-{uuid4().hex[:8]}"
        staged_audio = await _stage_upload(source_audio, intake_dir, "source_audio.mp3")
        staged_raw_text = await _stage_upload(raw_text, intake_dir, "raw_text.md")
        staged_notes = await _stage_upload(style_notes, intake_dir, "project_setup_notes.md") if style_notes else None
        effective_audio = _trim_audio_for_time_range(staged_audio, intake_dir, time_range)
        payload = _run_audio_text_bootstrap(
            config,
            project_name=project_name,
            source_audio=effective_audio,
            raw_text=staged_raw_text,
            setup_notes=staged_notes,
            profile=profile,
            time_range=time_range,
        )
        app_state.upsert_user_preference(
            key="studio_preferences",
            value={
                "default_profile": profile or config.default_profile,
                "default_concurrency": concurrency,
                "default_real_generation": real_generation,
                "last_bootstrapped_project": payload.project_id,
                "last_intake_mode": "audio_text",
            },
            user_id=current.user.id,
        )
        app_state.record_audit_event(actor_user_id=current.user.id, event_type="project_audio_text_intake_created", target_type="project", target_id=payload.project_id, payload=payload.model_dump())
        _discover_projects(config, app_state)
        result = jobs.start_job(
            project_id=payload.project_id,
            command=build_cli_command(
                project_json_path=payload.project_json_path,
                action="run",
                from_stage="transcription",
                to_stage=to_stage or "render",
                profile=profile,
                start_sec=float(time_range["start_sec"]) if time_range.get("enabled") and not time_range.get("audio_pretrimmed") else None,
                end_sec=float(time_range["end_sec"]) if time_range.get("enabled") and not time_range.get("audio_pretrimmed") else None,
                real_generation=real_generation,
                concurrency=concurrency,
                resume=True,
            ),
            read_only=False,
            user_id=current.user.id,
        )
        message = "Audio/text project created and render pipeline started." if result.accepted else result.reason or "Pipeline run rejected."
        return AudioTextIntakeResponse(**payload.model_dump(), run_id=result.job.run_id, started=result.accepted, message=message).model_dump()

    @app.get("/api/projects/{project_id}")
    def project_details(project_id: str, _current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        return project.model_dump()

    @app.get("/api/projects/{project_id}/overview")
    def project_overview(project_id: str, _current: AuthSession = Depends(require_session)):
        project, path = resolve_project(project_id)
        pipeline_state = _build_pipeline_state(project, jobs, app_state)
        latest_outputs = [item.label for item in list_artifacts(path) if item.type in {"video", "render", "report", "timeline"}][:8]
        overview = app_state.build_project_overview(
            project=project,
            lifecycle_status=pipeline_state.lifecycle_status,
            pipeline_state=pipeline_state.model_dump(),
            latest_outputs=latest_outputs,
        )
        return overview.model_dump()

    @app.get("/api/projects/{project_id}/pipeline")
    def project_pipeline(project_id: str, _current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        return _build_pipeline_state(project, jobs, app_state).model_dump()

    @app.get("/api/projects/{project_id}/status")
    def project_status_compat(project_id: str, _current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        return _build_pipeline_state(project, jobs, app_state).model_dump()

    @app.get("/api/projects/{project_id}/pipeline-state")
    def project_pipeline_state_compat(project_id: str, _current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        return _build_pipeline_state(project, jobs, app_state).model_dump()

    @app.post("/api/projects/{project_id}/pipeline/actions")
    def project_pipeline_action(project_id: str, request: PipelineActionRequest, current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        if not project.project_json_path:
            raise ProductApiError(status_code=400, code="project_state_error", message="Limited-support project has no project.json for pipeline actions")
        state = _build_pipeline_state(project, jobs, app_state)
        result = jobs.start_job(
            project_id=project_id,
            command=_pipeline_action_command(project.project_json_path, request, state),
            read_only=request.action == "validate",
            user_id=current.user.id,
        )
        return _command_response(result, "Run accepted.", "Run rejected.").model_dump()

    @app.post("/api/projects/{project_id}/pipeline-action")
    def project_pipeline_action_compat(project_id: str, request: PipelineActionRequest, current: AuthSession = Depends(require_session)):
        return project_pipeline_action(project_id, request, current)

    @app.get("/api/projects/{project_id}/review")
    def project_review(project_id: str, _current: AuthSession = Depends(require_session)):
        project, path = resolve_project(project_id)
        payload = _review_queue_for_project(project_id=project_id, project_path=path, project_json_path=Path(project.project_json_path) if project.project_json_path else None, app_state=app_state)
        return payload.model_dump()

    @app.post("/api/projects/{project_id}/review/decisions")
    def project_save_review_decision(project_id: str, request: ReviewDecisionRequest, current: AuthSession = Depends(require_session)):
        _project, _path = resolve_project(project_id)
        payload = app_state.save_review_decision(
            project_id=project_id,
            item_id=request.item_id,
            source=request.source,
            decision=request.decision,
            note=request.note,
            payload=request.payload,
            user_id=current.user.id,
        )
        return payload.model_dump()

    @app.post("/api/projects/{project_id}/review-decisions")
    def project_save_review_decision_compat(project_id: str, request: ReviewDecisionRequest, current: AuthSession = Depends(require_session)):
        return project_save_review_decision(project_id, request, current)

    @app.get("/api/projects/{project_id}/review-decisions")
    def project_review_decisions(project_id: str, _current: AuthSession = Depends(require_session)):
        _project, _path = resolve_project(project_id)
        return [item.model_dump() for item in app_state.list_review_decisions(project_id)]

    @app.post("/api/projects/{project_id}/review/apply")
    def project_review_apply(project_id: str, request: ReviewApplyRequest, current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        if not project.project_json_path:
            raise ProductApiError(status_code=400, code="project_state_error", message="Limited-support project has no project.json for review")
        result = jobs.start_job(
            project_id=project_id,
            command=build_cli_command(project_json_path=project.project_json_path, action="review", dry_run=request.dry_run),
            read_only=False,
            user_id=current.user.id,
        )
        return _command_response(result, "Review run accepted.", "Review run rejected.").model_dump()

    @app.get("/api/projects/{project_id}/assets")
    def project_assets(project_id: str, _current: AuthSession = Depends(require_session)):
        _project, path = resolve_project(project_id)
        entries = list_artifacts(path)
        payload: AssetCollection = app_state.sync_asset_index(project_id=project_id, entries=entries)
        return payload.model_dump()

    @app.get("/api/projects/{project_id}/artifacts")
    def project_artifacts_compat(project_id: str, _current: AuthSession = Depends(require_session)):
        _project, path = resolve_project(project_id)
        return [item.model_dump() for item in list_artifacts(path)]

    @app.get("/api/projects/{project_id}/timeline")
    def project_timeline(project_id: str, _current: AuthSession = Depends(require_session)):
        project, path = resolve_project(project_id)
        payload = load_timeline(project_id, path, Path(project.project_json_path) if project.project_json_path else None)
        return payload.model_dump()

    @app.get("/api/runs")
    def list_runs(limit: int = Query(default=50, ge=1, le=200), _current: AuthSession = Depends(require_session)):
        return [item.model_dump() for item in app_state.list_runs(limit=limit)]

    @app.get("/api/projects/{project_id}/runs")
    def list_project_runs(project_id: str, limit: int = Query(default=50, ge=1, le=200), _current: AuthSession = Depends(require_session)):
        _project, _path = resolve_project(project_id)
        return [item.model_dump() for item in app_state.list_runs(project_id=project_id, limit=limit)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, _current: AuthSession = Depends(require_session)):
        try:
            run = app_state.get_run(run_id, log_tail=jobs.read_logs(run_id, tail=200))
            return run.model_dump()
        except KeyError:
            raise ProductApiError(status_code=404, code="filesystem_error", message="Run not found", details={"run_id": run_id})

    @app.get("/api/runs/{run_id}/logs")
    def get_run_logs(run_id: str, tail: int = Query(default=200, ge=1, le=1000), _current: AuthSession = Depends(require_session)):
        try:
            return {"run_id": run_id, "lines": jobs.read_logs(run_id, tail=tail)}
        except KeyError:
            raise ProductApiError(status_code=404, code="filesystem_error", message="Run not found", details={"run_id": run_id})

    @app.get("/api/jobs")
    def list_jobs_compat(project_id: str | None = None, limit: int | None = Query(default=None, ge=1, le=100), _current: AuthSession = Depends(require_session)):
        return [item.model_dump() for item in jobs.list_jobs(project_id=project_id, limit=limit)]

    @app.get("/api/projects/{project_id}/jobs")
    def list_project_jobs_compat(project_id: str, limit: int = Query(default=20, ge=1, le=100), _current: AuthSession = Depends(require_session)):
        _project, _path = resolve_project(project_id)
        return [item.model_dump() for item in jobs.list_jobs(project_id=project_id, limit=limit)]

    @app.get("/api/jobs/{run_id}")
    def get_job_compat(run_id: str, _current: AuthSession = Depends(require_session)):
        try:
            return jobs.get_job(run_id).model_dump()
        except KeyError:
            raise ProductApiError(status_code=404, code="filesystem_error", message="Run not found", details={"run_id": run_id})

    @app.get("/api/jobs/{run_id}/logs")
    def get_job_logs_compat(run_id: str, tail: int = Query(default=200, ge=1, le=1000), _current: AuthSession = Depends(require_session)):
        return get_run_logs(run_id, tail, _current)

    @app.post("/api/projects/{project_id}/validate")
    def project_validate(project_id: str, request: ValidateRequest, current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        if not project.project_json_path:
            raise ProductApiError(status_code=400, code="project_state_error", message="Limited-support project has no project.json for validate")
        result = jobs.start_job(
            project_id=project_id,
            command=build_cli_command(project_json_path=project.project_json_path, action="validate", stage=request.stage),
            read_only=True,
            user_id=current.user.id,
        )
        return _command_response(result, "Validation accepted.", "Validation rejected.").model_dump()

    @app.post("/api/projects/{project_id}/run")
    def project_run(project_id: str, request: RunRequest, current: AuthSession = Depends(require_session)):
        project, _path = resolve_project(project_id)
        if not project.project_json_path:
            raise ProductApiError(status_code=400, code="project_state_error", message="Limited-support project has no project.json for run")
        result = jobs.start_job(
            project_id=project_id,
            command=build_cli_command(
                project_json_path=project.project_json_path,
                action="run",
                from_stage=request.from_stage,
                to_stage=request.to_stage,
                profile=request.profile,
                limit_frames=request.limit_frames,
                real_generation=request.real_generation,
                concurrency=request.concurrency,
                resume=request.resume,
                retry_failed_only=request.retry_failed_only,
                render_dry_run=request.render_dry_run,
                dry_run=request.dry_run,
            ),
            read_only=False,
            user_id=current.user.id,
        )
        return _command_response(result, "Pipeline run accepted.", "Pipeline run rejected.").model_dump()

    @app.get("/api/settings")
    def get_settings(_current: AuthSession = Depends(require_session)):
        return [item.model_dump() for item in app_state.get_settings()]

    @app.patch("/api/settings")
    def update_settings(request: SettingsUpdateRequest, current: AuthSession = Depends(require_session)):
        preference = app_state.upsert_user_preference(
            key="studio_preferences",
            value={
                "default_profile": request.default_profile or config.default_profile,
                "default_concurrency": request.default_concurrency or config.default_concurrency,
                "default_real_generation": bool(request.default_real_generation),
            },
            user_id=current.user.id,
        )
        return preference.model_dump()

    @app.get("/api/projects/{project_id}/preview")
    def preview(project_id: str, path: str, _current: AuthSession = Depends(require_session)):
        _project, project_path = resolve_project(project_id)
        candidate = Path(path).resolve(strict=False)
        try:
            candidate.relative_to(project_path.resolve(strict=False))
        except ValueError as exc:
            raise ProductApiError(status_code=403, code="filesystem_error", message="Preview path is outside the project") from exc
        if not candidate.exists() or not candidate.is_file():
            raise ProductApiError(status_code=404, code="filesystem_error", message="Preview file not found")
        payload = preview_file(candidate)
        return payload.model_dump()

    @app.get("/api/projects/{project_id}/media")
    def media(project_id: str, path: str, _current: AuthSession = Depends(require_session)):
        _project, project_path = resolve_project(project_id)
        candidate = Path(path).resolve(strict=False)
        try:
            candidate.relative_to(project_path.resolve(strict=False))
        except ValueError as exc:
            raise ProductApiError(status_code=403, code="filesystem_error", message="Media path is outside the project") from exc
        if not candidate.exists() or not candidate.is_file():
            raise ProductApiError(status_code=404, code="filesystem_error", message="Media file not found")
        return FileResponse(candidate)

    dist_dir = config.repo_root / "web" / "app" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="studio")

    return app
