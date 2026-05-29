"""Production dashboard for yt_nonstop projects.

This module intentionally lives in ``src/yt_nonstop``.  ``scripts/project_status.py``
is only a CLI wrapper.  The dashboard combines canonical JSON artifacts with the
optional project-local SQLite runtime state so long runs can be inspected without
opening many files by hand.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from yt_nonstop.pipeline.artifact_paths import STAGE_SEQUENCE
from yt_nonstop.pipeline.orchestrator import stage_hash_snapshot
from yt_nonstop.pipeline.project_config import load_project
from yt_nonstop.review.policy import summarize_review_blockers
from yt_nonstop.state.pipeline_state import (
    connect as connect_state_db,
    get_frame_states_for_project,
    get_stage_states_for_project,
    resolve_stale_stages,
    resolve_state_db_path,
    stage_state_to_dict,
    state_to_dict,
    summarize_states,
)
from yt_nonstop.utils.json_io import load_json


GENERATIVE_DECISIONS = {
    "new_image",
    "new_angle_same_setup",
    "detail_insert",
    "reaction_shot",
    "establishing_shot",
    "manual_asset",
}
NON_GENERATIVE_DECISIONS = {"hold_previous", "continuation_motion"}


@dataclass(frozen=True)
class StatusDashboard:
    project_id: str
    project_json: str
    current_stage: str
    workflow_profile: str
    state_db_path: str
    state_db_exists: bool
    state_stage: str
    narration_beats_count: int
    visual_slots_count: int
    new_image_slots_count: int
    hold_slots_count: int
    continuation_slots_count: int
    planned_variants_count: int
    generated_images_success: int
    generated_images_total: int
    generated_images_failed: int
    selected_images_count: int
    selected_images_expected: int
    selected_use_count: int
    manual_review_count: int
    rejected_or_excluded_count: int
    failed_frames_count: int
    continuity_warnings_count: int
    continuity_errors_count: int
    render_status: str
    render_ready: bool
    final_video_path: str
    state_summary: dict[str, Any]
    stage_state_summary: dict[str, Any]
    stage_states: list[dict[str, Any]]
    stale_stages: list[str]
    failed_frames: list[dict[str, Any]]
    blocked: list[str]
    warnings: list[str]
    info: list[str]
    ready_for_generation: bool
    ready_for_qc: bool
    ready_for_render: bool
    ready_for_human_review: bool
    completed: bool
    next_stage: str
    next_command: str
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Backward-compatible aliases for the original SQLite-only status CLI.
        payload.setdefault("exists", self.state_db_exists)
        payload.setdefault("summary", self.state_summary)
        payload.setdefault("stage", self.state_stage)
        return payload


def _read_json(path: str | Path | None, default: Any) -> Any:
    if not path:
        return default
    try:
        resolved = Path(path)
    except TypeError:
        return default
    if not resolved.exists():
        return default
    try:
        return load_json(resolved)
    except Exception:
        return default


def _rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get(key, [])
    else:
        value = payload
    return value if isinstance(value, list) else []


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _normalize_generation_manifest(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("generated_images", "images", "records", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _visual_allocation_metrics(project: dict[str, Any]) -> tuple[int, int, int, int, int]:
    allocation = _read_json(project.get("planning", {}).get("visual_allocation_plan_path"), {})
    metrics = allocation.get("metrics", {}) if isinstance(allocation, dict) else {}
    slots = _rows(allocation, "visual_slots")
    visual_slots_count = int(metrics.get("visual_slots_count") or len(slots) or 0)
    new_image_slots_count = int(metrics.get("new_image_slots_count") or 0)
    hold_or_continuation = int(metrics.get("hold_or_continuation_slots_count") or 0)
    planned_variants_count = int(metrics.get("planned_variants_count") or 0)

    if slots:
        if not new_image_slots_count:
            new_image_slots_count = sum(1 for slot in slots if _clean(slot.get("generation_decision")) in GENERATIVE_DECISIONS)
        if not hold_or_continuation:
            hold_or_continuation = sum(1 for slot in slots if _clean(slot.get("generation_decision")) in NON_GENERATIVE_DECISIONS)
        if not planned_variants_count:
            planned_variants_count = sum(
                max(0, int(slot.get("variant_count", 0) or 0))
                for slot in slots
                if _clean(slot.get("generation_decision")) in GENERATIVE_DECISIONS
            )
    hold_slots_count = sum(1 for slot in slots if _clean(slot.get("generation_decision")) == "hold_previous")
    continuation_slots_count = sum(1 for slot in slots if _clean(slot.get("generation_decision")) == "continuation_motion")
    if not hold_slots_count and not continuation_slots_count and hold_or_continuation:
        hold_slots_count = hold_or_continuation
    return visual_slots_count, new_image_slots_count, hold_slots_count, continuation_slots_count, planned_variants_count


def _state_payload(
    project_json: Path,
    project: dict[str, Any],
    stage: str,
    state_db_override: str | None = None,
) -> tuple[str, bool, dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[str]]:
    state_db_path = resolve_state_db_path(project_json, project, state_db_override)
    if not state_db_path.exists():
        return str(state_db_path), False, {"total": 0, "by_status": {}}, [], {"total": 0, "by_status": {}}, [], []
    conn = connect_state_db(state_db_path)
    try:
        resolve_stale_stages(
            conn,
            project_id=str(project.get("project_id", "")),
            ordered_stage_hashes=stage_hash_snapshot(project_json, project, STAGE_SEQUENCE),
        )
        states = get_frame_states_for_project(conn, project_id=str(project.get("project_id", "")), stage=stage)
        stage_states = get_stage_states_for_project(conn, project_id=str(project.get("project_id", "")))
        summary = summarize_states(states)
        failed = [state_to_dict(state) for state in states if state.status == "failed"]
        stage_summary = summarize_states(stage_states)
        serialized_stage_states = [stage_state_to_dict(state) for state in stage_states]
        stale_stages = [state["stage_name"] for state in serialized_stage_states if state.get("status") == "stale"]
        return str(state_db_path), True, summary, failed, stage_summary, serialized_stage_states, stale_stages
    finally:
        conn.close()


def _stage_artifact_missing(project: dict[str, Any], stage: str) -> bool:
    planning = project.get("planning", {})
    prompts = project.get("prompts", {})
    images = project.get("images", {})
    render = project.get("render", {})
    qc = project.get("qc", {})
    stage_to_path = {
        "build_narration_beats": planning.get("narration_beats_path"),
        "build_visual_shot_plan": prompts.get("visual_shot_plan_path"),
        "build_frame_briefs": planning.get("frame_briefs_json_path"),
        "generation_lock": prompts.get("generation_locked_json_path"),
        "image_qc": images.get("image_qc_report_path"),
        "normalize_images": images.get("selected_images_manifest_path"),
        "timeline": render.get("edit_decision_list_path"),
    }
    path = stage_to_path.get(stage)
    if not path:
        return False
    return not Path(path).exists()


def _resolve_next_stage(
    project: dict[str, Any],
    *,
    render_ready: bool,
    effective_selected: list[dict[str, Any]],
    stage_states: list[dict[str, Any]],
    stale_stages: list[str],
) -> str:
    if stale_stages:
        return stale_stages[0]
    for state in stage_states:
        if state.get("status") in {"failed", "running"}:
            return str(state.get("stage_name") or project.get("current_stage") or "generate_images")
    priority = [
        "build_narration_beats",
        "build_visual_shot_plan",
        "build_frame_briefs",
        "generation_lock",
        "generate_images",
        "image_qc",
        "normalize_images",
        "timeline",
        "render",
    ]
    for stage in priority:
        if stage == "generate_images":
            if effective_selected or project.get("images", {}).get("status") in {"generated", "normalized"}:
                continue
            return stage
        if stage == "render" and render_ready:
            continue
        if _stage_artifact_missing(project, stage):
            return stage
    current = str(project.get("current_stage", "")).strip()
    if current in STAGE_SEQUENCE:
        return current
    return "done" if render_ready else "generate_images"


def _next_command_for(project_json: Path, next_stage: str, *, failed_frames: list[dict[str, Any]], blocked: list[str]) -> str:
    project_arg = f'python scripts/run_fastgen_only_project.py --project-json "{project_json}"'
    if failed_frames:
        return f'{project_arg} --from generate_images --to generate_images --resume --retry-failed-only'
    if any("review" in item.lower() for item in blocked):
        return f'python scripts/project_status.py --project-json "{project_json}"'
    if next_stage == "generate_images":
        return f'{project_arg} --from generate_images --to generate_images --resume'
    if next_stage in {"timeline", "render"}:
        return f'{project_arg} --from {next_stage} --to render --resume'
    return f'{project_arg} --from {next_stage} --to {next_stage}'


def build_project_status(project_json: Path, *, stage: str = "generate_images", state_db_override: str | None = None) -> StatusDashboard:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)

    narration = _read_json(project.get("planning", {}).get("narration_beats_path"), {})
    narration_beats_count = len(_rows(narration, "beats"))
    visual_slots_count, new_image_slots_count, hold_slots_count, continuation_slots_count, planned_variants_count = _visual_allocation_metrics(project)

    run_manifest_path = project.get("images", {}).get("run_manifest_path")
    run_manifest_payload = _read_json(run_manifest_path, None) if run_manifest_path else None
    if run_manifest_payload is None:
        project_root = Path(str(project.get("meta", {}).get("project_root") or project_json.parent))
        for candidate in (project_root / "images" / "run" / "run_manifest.json", project_root / "images" / "run_manifest.json"):
            if candidate.exists():
                run_manifest_payload = _read_json(candidate, [])
                break
    generated_rows = _normalize_generation_manifest(run_manifest_payload if run_manifest_payload is not None else [])
    generated_success = sum(1 for row in generated_rows if _clean(row.get("status")).lower() == "success")
    generated_failed = sum(1 for row in generated_rows if _clean(row.get("status")).lower() not in {"", "success", "skipped_existing"})

    selected_rows = _rows(_read_json(project.get("images", {}).get("selected_images_manifest_path"), {}), "selected_images")
    review_rows = _rows(_read_json(project.get("qc", {}).get("review_applied_manifest_path"), {}), "selected_images")
    effective_selected = review_rows or selected_rows
    selected_use_count = sum(1 for row in effective_selected if _clean(row.get("selection_status")).lower() == "use")
    manual_review_count = sum(1 for row in effective_selected if _clean(row.get("selection_status")).lower() == "manual_review")
    rejected_or_excluded_count = sum(
        1
        for row in effective_selected
        if _clean(row.get("selection_status")).lower() in {"reject", "regenerate", "manual_replace"} or bool(row.get("render_excluded"))
    )

    continuity = _read_json(project.get("qc", {}).get("continuity_qc_report_path"), {})
    continuity_warnings = len(continuity.get("warnings", [])) if isinstance(continuity, dict) else 0
    continuity_errors = len(continuity.get("errors", [])) if isinstance(continuity, dict) else 0
    regeneration = _read_json(project.get("qc", {}).get("regeneration_plan_path"), {"tasks": []})
    regeneration_tasks = regeneration.get("tasks", []) if isinstance(regeneration, dict) else []

    render_report = _read_json(project.get("render", {}).get("render_report_json_path"), {})
    final_video = Path(str(project.get("render", {}).get("final_video_path", "")))
    render_status = _clean(project.get("render", {}).get("status") or render_report.get("status") or "pending") or "pending"
    render_ready = bool(render_status == "completed" and final_video.exists()) or bool(isinstance(render_report, dict) and render_report.get("dry_run"))

    state_db_path, state_db_exists, state_summary, failed_frames, stage_state_summary, stage_states, stale_stages = _state_payload(
        project_json, project, stage, state_db_override
    )

    selected_expected = visual_slots_count or len(effective_selected)
    blocked: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    next_actions: list[str] = []
    if not visual_slots_count:
        blocked.append("visual allocation plan is missing")
    if planned_variants_count and generated_success < planned_variants_count:
        warnings.append("not all planned variants have been generated yet")
    if failed_frames:
        blocked.append(f"{len(failed_frames)} frames failed generation")
    if stale_stages:
        warnings.append(f"{len(stale_stages)} stage(s) are stale after artifact changes")
    review_policy = summarize_review_blockers(project, effective_selected, regeneration_tasks)
    if rejected_or_excluded_count:
        blocked.append(f"{rejected_or_excluded_count} review decisions currently exclude render")
    if review_policy["regeneration_blocking"]:
        blocked.append(f"{len(regeneration_tasks)} regeneration/review task(s) still block render")
    if manual_review_count and not review_policy["manual_review_render_allowed"]:
        blocked.append(f"{manual_review_count} manual review item(s) must be resolved before render")
    elif manual_review_count:
        warnings.append(f"{manual_review_count} frames are still in manual review")
    if continuity_errors:
        blocked.append(f"continuity has {continuity_errors} error(s)")
    elif continuity_warnings:
        warnings.append(f"continuity has {continuity_warnings} warning(s)")
    if not render_ready and effective_selected:
        info.append("selected images exist; timeline/render can continue when blockers are cleared")
    if render_ready:
        info.append("render is ready or already completed")
    if not blocked and not warnings:
        info.append("no blocking status issues detected")
    next_stage = _resolve_next_stage(
        project,
        render_ready=render_ready,
        effective_selected=effective_selected,
        stage_states=stage_states,
        stale_stages=stale_stages,
    )
    next_command = _next_command_for(project_json, next_stage, failed_frames=failed_frames, blocked=blocked)
    next_actions.extend(blocked + warnings + info)
    ready_for_generation = next_stage == "generate_images" and not blocked
    ready_for_qc = next_stage == "image_qc" and not blocked
    ready_for_render = next_stage in {"timeline", "render"} and not blocked
    ready_for_human_review = manual_review_count > 0 or rejected_or_excluded_count > 0 or review_policy["regeneration_blocking"]
    completed = render_ready and not blocked

    return StatusDashboard(
        project_id=str(project.get("project_id", "")),
        project_json=str(project_json),
        current_stage=str(project.get("current_stage", "")),
        workflow_profile=str(project.get("workflow", {}).get("profile", "custom")),
        state_db_path=state_db_path,
        state_db_exists=state_db_exists,
        state_stage=stage,
        narration_beats_count=narration_beats_count,
        visual_slots_count=visual_slots_count,
        new_image_slots_count=new_image_slots_count,
        hold_slots_count=hold_slots_count,
        continuation_slots_count=continuation_slots_count,
        planned_variants_count=planned_variants_count,
        generated_images_success=generated_success,
        generated_images_total=len(generated_rows),
        generated_images_failed=generated_failed,
        selected_images_count=len(effective_selected),
        selected_images_expected=selected_expected,
        selected_use_count=selected_use_count,
        manual_review_count=manual_review_count,
        rejected_or_excluded_count=rejected_or_excluded_count,
        failed_frames_count=len(failed_frames),
        continuity_warnings_count=continuity_warnings,
        continuity_errors_count=continuity_errors,
        render_status=render_status,
        render_ready=render_ready,
        final_video_path=str(final_video) if str(final_video) else "",
        state_summary=state_summary,
        stage_state_summary=stage_state_summary,
        stage_states=stage_states,
        stale_stages=stale_stages,
        failed_frames=failed_frames,
        blocked=blocked,
        warnings=warnings,
        info=info,
        ready_for_generation=ready_for_generation,
        ready_for_qc=ready_for_qc,
        ready_for_render=ready_for_render,
        ready_for_human_review=ready_for_human_review,
        completed=completed,
        next_stage=next_stage,
        next_command=next_command,
        next_actions=next_actions,
    )


def format_project_status(status: StatusDashboard, *, include_failed: bool = False) -> str:
    lines = [
        f"Project: {status.project_id}",
        f"Current stage: {status.current_stage or 'unknown'}",
        f"Profile: {status.workflow_profile}",
        "",
        f"narration beats: {status.narration_beats_count}",
        f"visual slots: {status.visual_slots_count}",
        f"new image slots: {status.new_image_slots_count}",
        f"hold slots: {status.hold_slots_count}",
        f"continuation slots: {status.continuation_slots_count}",
        f"planned variants: {status.planned_variants_count}",
        f"generated images: {status.generated_images_success} / {status.planned_variants_count or status.generated_images_total}",
        f"selected images: {status.selected_images_count} / {status.selected_images_expected}",
        f"manual review: {status.manual_review_count}",
        f"render excluded: {status.rejected_or_excluded_count}",
        f"failed frames: {status.failed_frames_count}",
        f"continuity warnings: {status.continuity_warnings_count}",
        f"continuity errors: {status.continuity_errors_count}",
        f"render status: {status.render_status}",
        f"render ready: {str(status.render_ready).lower()}",
        f"state stage: {status.state_stage}",
        f"state db: {status.state_db_path} ({'exists' if status.state_db_exists else 'missing'})",
        f"ready for generation: {str(status.ready_for_generation).lower()}",
        f"ready for qc: {str(status.ready_for_qc).lower()}",
        f"ready for render: {str(status.ready_for_render).lower()}",
        f"ready for human review: {str(status.ready_for_human_review).lower()}",
        f"completed: {str(status.completed).lower()}",
        f"next stage: {status.next_stage}",
    ]
    if status.state_summary.get("by_status"):
        lines.append("state counts:")
        for key, value in sorted(status.state_summary.get("by_status", {}).items()):
            lines.append(f"  {key}: {value}")
    if status.stage_state_summary.get("by_status"):
        lines.append("stage state counts:")
        for key, value in sorted(status.stage_state_summary.get("by_status", {}).items()):
            lines.append(f"  {key}: {value}")
    if status.stale_stages:
        lines.append("stale stages:")
        for item in status.stale_stages:
            lines.append(f"  - {item}")
    if include_failed:
        lines.append("Failed frames:")
        if not status.failed_frames:
            lines.append("  none")
        for item in status.failed_frames:
            lines.append(
                "  {frame_id} | slot={visual_slot_id} | attempts={attempt_count} | error={error_message}".format(**item)
            )
    lines.append("")
    lines.append("BLOCKED:")
    if status.blocked:
        for item in status.blocked:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("WARNING:")
    if status.warnings:
        for item in status.warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("INFO:")
    if status.info:
        for item in status.info:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Next actions:")
    for item in status.next_actions:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(f"NEXT COMMAND: {status.next_command}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print a production dashboard for a yt_nonstop project.")
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--stage", default="generate_images", help="Runtime-state stage to summarize from pipeline_state.sqlite.")
    parser.add_argument("--state-db", default="", help="Override project-local pipeline_state.sqlite path.")
    parser.add_argument("--failed", action="store_true", help="Show failed runtime-state frames.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    dashboard = build_project_status(Path(args.project_json), stage=args.stage, state_db_override=args.state_db or None)
    if args.json:
        print(json.dumps(dashboard.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_project_status(dashboard, include_failed=args.failed))


if __name__ == "__main__":  # pragma: no cover
    main()
