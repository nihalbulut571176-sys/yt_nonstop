from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from yt_nonstop.pipeline.project_config import load_project
from yt_nonstop.pipeline.project_status import build_project_status
from yt_nonstop.webapi.app_state import lifecycle_status_for
from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.models import ProjectDetails, ProjectSummary


PROJECT_MARKERS = ("input", "work", "images", "output")


def _iso_from_ts(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _stable_project_id(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve(strict=False)).encode("utf-8")).hexdigest()[:10]
    return f"proj-{digest}"


def _available_outputs(path: Path) -> list[str]:
    outputs: list[str] = []
    for label, target in (
        ("input", path / "input"),
        ("work", path / "work"),
        ("images", path / "images"),
        ("final_images", path / "final_images"),
        ("output", path / "output"),
        ("renders", path / "renders"),
    ):
        if target.exists():
            outputs.append(label)
    return outputs


def _classify_project(path: Path) -> tuple[str, str, Path | None]:
    project_json = path / "project.json"
    if project_json.exists():
        return "repo-native", "full", project_json
    markers = sum(1 for marker in PROJECT_MARKERS if (path / marker).exists())
    if markers >= 2:
        return "artifact-workspace", "limited", None
    return "", "", None


def discover_projects(config: WebConfig) -> list[ProjectSummary]:
    workspace_root = config.workspace_root
    if not workspace_root.exists():
        return []
    projects: list[ProjectSummary] = []
    for child in sorted(workspace_root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        kind, support, project_json = _classify_project(child)
        if not kind:
            continue
        stat = child.stat()
        project_id = _stable_project_id(child)
        name = child.name
        status = "limited_support"
        current_stage = None
        next_stage = None
        blocked_count = 0
        warning_count = 0
        lifecycle_status = "draft" if support == "limited" else "ready_for_validation"
        if project_json:
            try:
                project = load_project(project_json)
                status = str(project.get("current_stage") or "ready")
                project_id = str(project.get("project_id") or project_id)
                name = str(project.get("project_name") or project.get("project_id") or name)
                dashboard = build_project_status(project_json)
                current_stage = dashboard.current_stage
                next_stage = dashboard.next_stage
                blocked_count = len(dashboard.blocked)
                warning_count = len(dashboard.warnings)
                lifecycle_status = lifecycle_status_for(
                    support=support,
                    blocked=dashboard.blocked,
                    ready_for_render=dashboard.ready_for_render,
                    ready_for_human_review=dashboard.ready_for_human_review,
                    completed=dashboard.completed,
                    active_run=None,
                    next_stage=dashboard.next_stage,
                )
            except Exception:
                status = "project_json_error"
        projects.append(
            ProjectSummary(
                id=project_id,
                name=name,
                path=str(child.resolve(strict=False)),
                kind=kind,
                support=support,
                status=status,
                last_updated=_iso_from_ts(stat.st_mtime),
                available_outputs=_available_outputs(child),
                project_json_path=str(project_json.resolve(strict=False)) if project_json else None,
                current_stage=current_stage,
                next_stage=next_stage,
                blocked_count=blocked_count,
                warning_count=warning_count,
                lifecycle_status=lifecycle_status,
            )
        )
    return projects


def get_project(config: WebConfig, project_id: str) -> ProjectDetails:
    projects = discover_projects(config)
    for item in projects:
        if item.id != project_id:
            continue
        dashboard = None
        current_stage = None
        next_stage = None
        next_command = None
        markers = item.available_outputs.copy()
        payload = item.model_dump()
        if item.project_json_path:
            try:
                status = build_project_status(Path(item.project_json_path))
                dashboard = status.to_dict()
                current_stage = status.current_stage
                next_stage = status.next_stage
                next_command = status.next_command
            except Exception as exc:
                markers.append(f"status_error:{exc.__class__.__name__}")
        payload["current_stage"] = current_stage or payload.get("current_stage")
        payload["next_stage"] = next_stage or payload.get("next_stage")
        return ProjectDetails(
            **payload,
            markers=markers,
            next_command=next_command,
            dashboard=dashboard,
        )
    raise KeyError(project_id)
