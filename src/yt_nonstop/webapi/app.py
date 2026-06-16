from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from yt_nonstop.pipeline.project_status import build_project_status
from yt_nonstop.webapi.app_state import AppStateStore, AuthSession, lifecycle_status_for
from yt_nonstop.webapi.artifacts import list_artifacts, load_review, load_timeline, preview_file
from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.jobs import JobStore, build_cli_command
from yt_nonstop.webapi.models import (
    ApiErrorEnvelope,
    AssetCollection,
    CommandResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    PipelineAction,
    PipelineActionRequest,
    PipelineState,
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
        return [
            PipelineAction(
                key="limited_support",
                label="Limited support project",
                enabled=False,
                reason="This project has no project.json, so CLI-backed pipeline actions are disabled.",
            )
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


def _discover_projects(config: WebConfig, app_state: AppStateStore):
    projects = discover_projects(config)
    app_state.sync_projects(projects)
    return projects


def _build_pipeline_state(project, jobs: JobStore, app_state: AppStateStore) -> PipelineState:
    active_run = jobs.active_job_for_project(project.id)
    recent_runs = app_state.list_runs(project_id=project.id, limit=10)
    if not project.project_json_path:
        lifecycle_status = lifecycle_status_for(
            support=project.support,
            blocked=["Project has limited support in the studio because no project.json was discovered."],
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
            blocked=["Project has limited support in the studio because no project.json was discovered."],
            warnings=[],
            info=["Artifact browsing remains available.", "CLI-backed write actions are disabled for limited-support projects."],
            blocked_count=1,
            warning_count=0,
            active_run=active_run,
            recent_runs=recent_runs,
        )
        state.available_actions = _available_pipeline_actions(project, state)
        return state

    dashboard = build_project_status(Path(project.project_json_path))
    lifecycle_status = lifecycle_status_for(
        support=project.support,
        blocked=dashboard.blocked,
        ready_for_render=dashboard.ready_for_render,
        ready_for_human_review=dashboard.ready_for_human_review,
        completed=dashboard.completed,
        active_run=active_run,
        next_stage=dashboard.next_stage,
    )
    app_state.update_project_snapshot(
        project_id=project.id,
        lifecycle_status=lifecycle_status,
        next_command=dashboard.next_command,
        dashboard=dashboard.to_dict(),
        blocked_count=len(dashboard.blocked),
        warning_count=len(dashboard.warnings),
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
        blocked=dashboard.blocked,
        warnings=dashboard.warnings,
        info=dashboard.info,
        blocked_count=len(dashboard.blocked),
        warning_count=len(dashboard.warnings),
        ready_for_generation=dashboard.ready_for_generation,
        ready_for_qc=dashboard.ready_for_qc,
        ready_for_render=dashboard.ready_for_render,
        ready_for_human_review=dashboard.ready_for_human_review,
        completed=dashboard.completed,
        active_run=active_run,
        recent_runs=recent_runs,
    )
    state.available_actions = _available_pipeline_actions(project, state)
    return state


def _pipeline_action_command(project_json_path: str, request: PipelineActionRequest) -> list[str]:
    if request.action == "validate":
        return build_cli_command(project_json_path=project_json_path, action="validate", stage="all")
    if request.action == "resume":
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


def _review_queue_for_project(*, project_id: str, project_path: Path, project_json_path: Path | None, app_state: AppStateStore) -> ReviewQueue:
    review_payload = load_review(project_id, project_path, project_json_path)
    timeline_payload = load_timeline(project_id, project_path, project_json_path)
    source = review_payload.source or timeline_payload.source
    raw_rows = review_payload.rows if review_payload.rows else timeline_payload.rows
    items = app_state.sync_review_items(project_id=project_id, source=source or "review", rows=raw_rows)
    decisions = app_state.list_review_decisions(project_id)
    summary = {"items": len(items), "decisions": len(decisions), "manual_review": 0, "regenerate": 0}
    for decision in decisions:
        if decision.decision == "manual_review":
            summary["manual_review"] += 1
        if decision.decision == "regenerate":
            summary["regenerate"] += 1
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
        result = jobs.start_job(
            project_id=project_id,
            command=_pipeline_action_command(project.project_json_path, request),
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
