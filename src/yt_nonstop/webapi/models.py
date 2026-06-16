from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ProjectKind = Literal["repo-native", "artifact-workspace"]
ProjectSupport = Literal["full", "limited"]
RunStatus = Literal["queued", "running", "completed", "failed", "rejected", "cancelled"]
UserRole = Literal["Operator", "Reviewer", "Admin"]
ProjectLifecycleStatus = Literal["draft", "ready_for_validation", "running", "awaiting_review", "ready_for_render", "rendering", "completed", "blocked", "failed"]
ReviewDecisionStatus = Literal["pending", "approved", "warning", "manual_review", "regenerate", "rejected", "finalized"]
ErrorCode = Literal["auth_error", "validation_error", "project_state_error", "run_conflict_error", "provider_error", "filesystem_error", "system_error"]


class ApiErrorEnvelope(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class ProjectSummary(BaseModel):
    id: str
    name: str
    path: str
    kind: ProjectKind
    support: ProjectSupport
    status: str
    lifecycle_status: ProjectLifecycleStatus | None = None
    last_updated: str | None = None
    available_outputs: list[str] = Field(default_factory=list)
    project_json_path: str | None = None
    current_stage: str | None = None
    next_stage: str | None = None
    blocked_count: int = 0
    warning_count: int = 0


class ProjectDetails(ProjectSummary):
    markers: list[str] = Field(default_factory=list)
    next_command: str | None = None
    dashboard: dict[str, Any] | None = None


class WorkspaceSummary(BaseModel):
    workspace_root: str
    total_projects: int
    full_support_projects: int
    limited_support_projects: int
    active_runs: int = 0
    blocked_projects: int = 0
    awaiting_review_projects: int = 0
    ready_for_render_projects: int = 0
    completed_projects: int = 0
    recent_project_ids: list[str] = Field(default_factory=list)


class ArtifactEntry(BaseModel):
    type: str
    label: str
    path: str
    size: int
    modified_at: str
    preview_kind: str


class AssetGroup(BaseModel):
    type: str
    label: str
    count: int
    entries: list[ArtifactEntry] = Field(default_factory=list)


class AssetCollection(BaseModel):
    project_id: str
    total_count: int
    groups: list[AssetGroup] = Field(default_factory=list)


class RunSummary(BaseModel):
    run_id: str
    project_id: str
    action_type: str
    command: list[str]
    status: RunStatus
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    log_path: str
    read_only: bool = False
    user_id: int | None = None
    username: str | None = None
    error_category: str | None = None


class RunEvent(BaseModel):
    event_id: int
    run_id: str
    event_type: str
    message: str
    created_at: str


class RunDetails(RunSummary):
    events: list[RunEvent] = Field(default_factory=list)
    log_tail: list[str] = Field(default_factory=list)


class PipelineAction(BaseModel):
    key: str
    label: str
    recommended: bool = False
    enabled: bool = True
    reason: str | None = None


class PipelineActionRequest(BaseModel):
    action: Literal["validate", "resume", "retry_failed_only", "render_dry_run", "run_range"]
    from_stage: str | None = None
    to_stage: str | None = None
    profile: str | None = None
    limit_frames: int = 0
    real_generation: bool = False
    concurrency: int = 10
    dry_run: bool = False


class CommandResponse(BaseModel):
    accepted: bool
    run_id: str
    state: RunStatus
    message: str


class RunRequest(BaseModel):
    from_stage: str | None = None
    to_stage: str = "render"
    profile: str | None = None
    limit_frames: int = 0
    real_generation: bool = False
    concurrency: int = 10
    resume: bool = False
    retry_failed_only: bool = False
    render_dry_run: bool = False
    dry_run: bool = False


class ValidateRequest(BaseModel):
    stage: str = "all"


class ReviewApplyRequest(BaseModel):
    dry_run: bool = False


class FilePreview(BaseModel):
    path: str
    preview_kind: str
    content: str | None = None
    lines: list[str] = Field(default_factory=list)


class TimelinePayload(BaseModel):
    project_id: str
    source: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ReviewPayload(BaseModel):
    project_id: str
    source: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ReviewItem(BaseModel):
    item_id: str
    label: str
    source: str
    status: str | None = None
    warning: str | None = None
    action: str | None = None
    image_path: str | None = None
    start: str | None = None
    end: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReviewDecision(BaseModel):
    id: int
    project_id: str
    item_id: str
    source: str
    decision: ReviewDecisionStatus
    note: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    user_id: int | None = None
    username: str | None = None
    created_at: str
    updated_at: str


class ReviewQueue(BaseModel):
    project_id: str
    source: str | None = None
    items: list[ReviewItem] = Field(default_factory=list)
    decisions: list[ReviewDecision] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    raw_rows: list[dict[str, Any]] = Field(default_factory=list)


class PipelineState(BaseModel):
    project_id: str
    project_name: str
    support: ProjectSupport
    lifecycle_status: ProjectLifecycleStatus
    current_stage: str | None = None
    next_stage: str | None = None
    next_command: str | None = None
    blocked: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)
    blocked_count: int = 0
    warning_count: int = 0
    ready_for_generation: bool = False
    ready_for_qc: bool = False
    ready_for_render: bool = False
    ready_for_human_review: bool = False
    completed: bool = False
    active_run: RunSummary | None = None
    recent_runs: list[RunSummary] = Field(default_factory=list)
    available_actions: list[PipelineAction] = Field(default_factory=list)


class UserRecord(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRole
    is_active: bool = True
    created_at: str
    updated_at: str


class SessionRecord(BaseModel):
    token: str
    user_id: int
    created_at: str
    expires_at: str
    last_seen_at: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user: UserRecord
    session: SessionRecord


class CreateProjectRequest(BaseModel):
    project_name: str
    source_srt_path: str
    source_audio_path: str | None = None
    raw_text_path: str | None = None
    setup_notes_path: str | None = None
    profile: str = "no_vlm_production"


class CreateProjectResponse(BaseModel):
    project_id: str
    project_name: str
    project_root: str
    project_json_path: str
    support: ProjectSupport
    next_route: str
    notes: list[str] = Field(default_factory=list)


class ProjectOverview(BaseModel):
    project_id: str
    project_name: str
    path: str
    kind: ProjectKind
    support: ProjectSupport
    lifecycle_status: ProjectLifecycleStatus
    current_stage: str | None = None
    next_stage: str | None = None
    next_command: str | None = None
    blocked: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latest_outputs: list[str] = Field(default_factory=list)
    latest_run: RunSummary | None = None
    recent_runs: list[RunSummary] = Field(default_factory=list)
    review_decision_count: int = 0
    active_run: RunSummary | None = None


class ReviewDecisionRequest(BaseModel):
    item_id: str
    source: str = "review"
    decision: ReviewDecisionStatus
    note: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdateRequest(BaseModel):
    default_profile: str | None = None
    default_concurrency: int | None = None
    default_real_generation: bool | None = None


class SettingRecord(BaseModel):
    category: Literal["workspace", "operator_preferences", "provider_metadata", "environment", "auth"]
    key: str
    provider: str | None = None
    value: dict[str, Any] = Field(default_factory=dict)
    updated_at: str
    updated_by_username: str | None = None
