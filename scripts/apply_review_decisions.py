import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project
from yt_nonstop.review.policy import (
    RENDER_BLOCKING_REVIEW_STATUSES,
    RENDER_BLOCKING_SELECTION_STATUSES,
    clean,
    selection_status_for_review,
)


VALID_REVIEW_STATUSES = {"approve", "regenerate", "manual_replace", "reject"}
def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_decision_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("decisions") or payload.get("frames") or []
    else:
        rows = []
    normalized: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        scene_id = clean(row.get("scene_id") or row.get("frame_id"))
        if not scene_id:
            continue
        status = clean(row.get("status") or row.get("review_status") or "approve").lower()
        if status not in VALID_REVIEW_STATUSES:
            raise RuntimeError(f"Invalid review status for {scene_id}: {status}. Expected one of {sorted(VALID_REVIEW_STATUSES)}")
        normalized.append({**row, "scene_id": scene_id, "status": status})
    return normalized


def load_decisions(decisions_path: Path) -> dict[str, dict[str, Any]]:
    if not decisions_path.exists():
        return {}
    rows = normalize_decision_rows(load_json(decisions_path))
    return {row["scene_id"]: row for row in rows}


def apply_review_decisions_to_project(project_json: Path, *, write_project: bool = True) -> dict[str, Any]:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    decisions_path_str = str(project["qc"].get("review_decisions_path", "") or "").strip()
    decisions_path = Path(decisions_path_str) if decisions_path_str else None
    selected_manifest_path = Path(project["images"].get("selected_images_manifest_path", ""))
    applied_manifest_path_str = str(project["qc"].get("review_applied_manifest_path", "") or "").strip()
    applied_manifest_path = Path(applied_manifest_path_str) if applied_manifest_path_str else None

    if not selected_manifest_path.exists():
        raise FileNotFoundError(f"selected_images_manifest not found: {selected_manifest_path}")

    selected_payload = load_json(selected_manifest_path)
    selected_rows = selected_payload.get("selected_images", []) if isinstance(selected_payload, dict) else []
    if not isinstance(selected_rows, list):
        raise RuntimeError("selected_images_manifest.json must contain a selected_images list")

    decisions_by_scene = load_decisions(decisions_path) if decisions_path else {}
    applied = 0
    approved = 0
    render_excluded = 0
    missing_selected_rows: list[str] = []

    selected_scene_ids = {clean(row.get("scene_id")) for row in selected_rows if isinstance(row, dict)}
    for scene_id in sorted(decisions_by_scene):
        if scene_id not in selected_scene_ids:
            missing_selected_rows.append(scene_id)

    for row in selected_rows:
        if not isinstance(row, dict):
            continue
        scene_id = clean(row.get("scene_id"))
        decision = decisions_by_scene.get(scene_id)
        if not decision:
            row.setdefault("human_review_status", "approve")
            row.setdefault("render_excluded", False)
            approved += 1 if clean(row.get("selection_status") or "use") in {"use", "manual_review"} else 0
            continue

        status = decision["status"]
        previous_status = clean(row.get("selection_status") or "use")
        row["human_review_status"] = status
        row["human_review_decision"] = {
            "status": status,
            "notes": decision.get("notes", ""),
            "replacement_image_path": decision.get("replacement_image_path", ""),
            "decided_by": decision.get("decided_by", ""),
            "decided_at": decision.get("decided_at", ""),
        }
        row["selection_status_before_human_review"] = previous_status
        row["selection_status"] = selection_status_for_review(status, previous_status)
        row["review_applied_at"] = iso_now()
        if status in RENDER_BLOCKING_REVIEW_STATUSES:
            row["render_excluded"] = True
            row["render_exclusion_reason"] = f"human_review_{status}"
            render_excluded += 1
        else:
            row["render_excluded"] = False
            row.pop("render_exclusion_reason", None)
            approved += 1
        applied += 1

    selected_payload["review_decisions_path"] = str(decisions_path) if decisions_path else ""
    selected_payload["review_applied_at"] = iso_now()
    selected_payload["review_applied_count"] = applied
    selected_payload["render_eligible_count"] = approved
    selected_payload["render_excluded_count"] = render_excluded
    selected_payload["review_missing_selected_rows"] = missing_selected_rows

    save_json(selected_manifest_path, selected_payload)
    if applied_manifest_path:
        save_json(applied_manifest_path, selected_payload)

    project.setdefault("qc", {})["human_review_status"] = "decisions_applied"
    project["qc"]["review_decisions_path"] = str(decisions_path) if decisions_path else ""
    project["qc"]["review_applied_manifest_path"] = str(applied_manifest_path) if applied_manifest_path else ""
    project["qc"]["review_applied_count"] = applied
    project["qc"]["review_render_excluded_count"] = render_excluded
    project["qc"]["review_missing_selected_rows"] = missing_selected_rows
    if write_project:
        save_project(project_json, project)

    return {
        "project_id": project.get("project_id"),
        "review_decisions_path": str(decisions_path) if decisions_path else "",
        "selected_images_manifest_path": str(selected_manifest_path),
        "review_applied_manifest_path": str(applied_manifest_path) if applied_manifest_path else "",
        "applied": applied,
        "approved": approved,
        "render_excluded": render_excluded,
        "missing_selected_rows": missing_selected_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()
    summary = apply_review_decisions_to_project(Path(args.project_json))
    print(summary)


if __name__ == "__main__":
    main()
