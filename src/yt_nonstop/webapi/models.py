from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ProjectKind = Literal["repo-native", "artifact-workspace"]
ProjectSupport = Literal["full", "limited"]
JobStatus = Literal["queued", "running", "completed", "failed", "rejected"]


class ProjectSummary(BaseModel):
    id: str
    name: str
    path: str
    kind: ProjectKind
    support: ProjectSupport
    status: str
    last_updated: str | None = None
    available_outputs: list[str] = Field(default_factory=list)
    project_json_path: str | None = None


class ProjectDetails(ProjectSummary):
    markers: list[str] = Field(default_factory=list)
    current_stage: str | None = None
    next_stage: str | None = None
    next_command: str | None = None
    dashboard: dict[str, Any] | None = None


class ArtifactEntry(BaseModel):
    type: str
    label: str
    path: str
    size: int
    modified_at: str
    preview_kind: str


class JobRecord(BaseModel):
    job_id: str
    project_id: str
    command: list[str]
    status: JobStatus
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    log_path: str
    read_only: bool = False


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
