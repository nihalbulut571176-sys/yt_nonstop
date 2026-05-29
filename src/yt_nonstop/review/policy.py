from __future__ import annotations

from typing import Any


RENDER_BLOCKING_REVIEW_STATUSES = {"regenerate", "manual_replace", "reject"}
RENDER_BLOCKING_SELECTION_STATUSES = {
    "regenerate",
    "manual_replace",
    "reject",
    "review_regenerate",
    "review_manual_replace",
    "review_reject",
}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def allow_manual_review_for_render(project: dict[str, Any]) -> bool:
    return bool(project.get("qc", {}).get("allow_manual_review_without_vlm", False))


def selection_status_for_review(status: str, previous_status: str) -> str:
    if status == "approve":
        return "use" if previous_status in RENDER_BLOCKING_SELECTION_STATUSES or previous_status == "manual_review" else (previous_status or "use")
    return f"review_{status}"


def selection_is_timeline_eligible(project: dict[str, Any], row: dict[str, Any]) -> bool:
    selection_status = clean(row.get("selection_status")).lower() or "use"
    if selection_status == "use":
        return row.get("render_excluded") is not True
    if selection_status == "manual_review":
        return allow_manual_review_for_render(project) and row.get("render_excluded") is not True
    return False


def selection_is_render_blocking(project: dict[str, Any], row: dict[str, Any]) -> bool:
    if row.get("render_excluded") is True:
        return True
    selection_status = clean(row.get("selection_status")).lower() or "use"
    human_review_status = clean(row.get("human_review_status")).lower()
    if human_review_status in RENDER_BLOCKING_REVIEW_STATUSES:
        return True
    if selection_status in RENDER_BLOCKING_SELECTION_STATUSES:
        return True
    if selection_status == "manual_review" and not allow_manual_review_for_render(project):
        return True
    if row.get("coverage_status") != "pass":
        return True
    return False


def regeneration_tasks_block_render(regeneration_tasks: list[dict[str, Any]]) -> bool:
    for task in regeneration_tasks:
        status = clean(task.get("status")).lower()
        action = clean(task.get("action")).lower()
        if status in {"queued", "manual_review", "pending", "failed"}:
            return True
        if action in {"rewrite_prompt_and_regenerate", "regenerate_variant", "manual_review"} and status != "completed":
            return True
    return False


def summarize_review_blockers(project: dict[str, Any], selected_rows: list[dict[str, Any]], regeneration_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    render_blocking = [row for row in selected_rows if selection_is_render_blocking(project, row)]
    manual_review_rows = [row for row in selected_rows if clean(row.get("selection_status")).lower() == "manual_review"]
    return {
        "render_blocking_count": len(render_blocking),
        "manual_review_count": len(manual_review_rows),
        "manual_review_render_allowed": allow_manual_review_for_render(project),
        "regeneration_blocking": regeneration_tasks_block_render(regeneration_tasks),
    }
