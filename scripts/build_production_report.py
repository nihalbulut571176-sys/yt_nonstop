import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project
from yt_nonstop.review.policy import summarize_review_blockers


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_payload(path_str: str | None, default: Any) -> Any:
    if not path_str:
        return default
    path = Path(path_str)
    if not path.exists():
        return default
    return load_json(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    json_path = Path(project["reports"]["production_report_json_path"])
    md_path = Path(project["reports"]["production_report_md_path"])

    selected = load_payload(project.get("images", {}).get("selected_images_manifest_path"), {}).get("selected_images", [])
    image_qc = load_payload(project.get("images", {}).get("image_qc_report_path"), {}).get("images", [])
    regen = load_payload(project.get("qc", {}).get("regeneration_plan_path"), {"tasks": []})
    continuity = load_payload(project.get("qc", {}).get("continuity_qc_report_path"), {})
    edl = load_payload(project.get("render", {}).get("edit_decision_list_path"), {}).get("edl", [])
    render_report = load_payload(project.get("render", {}).get("render_report_json_path"), {})
    allocation = load_payload(project.get("planning", {}).get("visual_allocation_plan_path"), {})
    run_manifest = load_payload(project.get("images", {}).get("run_manifest_path"), {})
    allocation_metrics = allocation.get("metrics", {}) if isinstance(allocation, dict) else {}
    visual_slots = allocation.get("visual_slots", []) if isinstance(allocation, dict) else []

    selected_count = len(selected)
    manual_review = sum(1 for item in selected if item.get("selection_status") == "manual_review")
    use_count = sum(1 for item in selected if item.get("selection_status") == "use")
    coverage_pass = sum(1 for item in selected if item.get("coverage_status") == "pass")
    semantic_flagged = sum(1 for item in selected if item.get("semantic_flags"))
    regen_tasks = regen.get("tasks", []) if isinstance(regen, dict) else []
    continuity_status = continuity.get("status", "missing") if isinstance(continuity, dict) else "missing"
    final_video = Path(project.get("render", {}).get("final_video_path", ""))
    render_status = project.get("render", {}).get("status", "unknown")
    render_ready = bool(render_status == "completed" and final_video.exists()) or bool(render_report.get("dry_run"))
    planned_generative_frames = int(run_manifest.get("planned_generative_frames_count", 0) or 0)
    completed_images = int(run_manifest.get("completed_count", 0) or 0)
    skipped_existing_success_count = int(run_manifest.get("skipped_existing_success_count", 0) or 0)
    limited_pilot = bool(run_manifest.get("limited_pilot"))
    partial_pilot = bool(run_manifest.get("partial_pilot"))
    pilot_generated_or_reused = completed_images if completed_images > 0 else skipped_existing_success_count

    review_policy = summarize_review_blockers(project, selected, regen_tasks)

    motion_types = sorted({str(row.get("motion_type") or row.get("motion") or "").strip() for row in edl if str(row.get("motion_type") or row.get("motion") or "").strip()})
    transition_styles = sorted({str(row.get("transition_style") or "").strip() for row in edl if str(row.get("transition_style") or "").strip()})
    motion_enabled_count = sum(1 for row in edl if str(row.get("motion_type") or row.get("motion") or "").strip() and str(row.get("motion_type") or row.get("motion") or "").strip() != "static_hold")

    metrics = {
        "narration_beats_count": int(allocation_metrics.get("narration_beats_count", 0) or 0),
        "visual_slots_count": int(allocation_metrics.get("visual_slots_count", len(visual_slots)) or len(visual_slots)),
        "new_image_slots_count": int(allocation_metrics.get("new_image_slots_count", 0) or 0),
        "hold_or_continuation_slots_count": int(allocation_metrics.get("hold_or_continuation_slots_count", 0) or 0),
        "planned_variants_count": int(allocation_metrics.get("planned_variants_count", 0) or 0),
        "average_visual_slot_duration": allocation_metrics.get("average_slot_duration", 0.0),
        "selected_images_count": selected_count,
        "selected_use_count": use_count,
        "manual_review_count": manual_review,
        "coverage_pass_rate": round(coverage_pass / selected_count, 4) if selected_count else 0.0,
        "semantic_flagged_count": semantic_flagged,
        "regeneration_tasks_count": len(regen_tasks),
        "continuity_status": continuity_status,
        "continuity_warning_count": len(continuity.get("warnings", [])) if isinstance(continuity, dict) else 0,
        "continuity_error_count": len(continuity.get("errors", [])) if isinstance(continuity, dict) else 0,
        "edl_frames_count": len(edl),
        "motion_enabled_frames_count": motion_enabled_count,
        "motion_types": motion_types,
        "transition_styles": transition_styles,
        "render_mode": render_report.get("render_mode") or project.get("render", {}).get("render_mode", "unknown"),
        "qc_images_count": len(image_qc),
        "render_ready": render_ready,
        "render_status": render_status,
        "final_video_path": str(final_video) if str(final_video) else "",
        "workflow_profile": project.get("workflow", {}).get("profile", "custom"),
        "image_semantic_qc_mode": project.get("qc", {}).get("image_semantic_qc_mode", "heuristic"),
        "render_blocking_selected_count": review_policy["render_blocking_count"],
        "manual_review_render_allowed": review_policy["manual_review_render_allowed"],
        "regeneration_blocking": review_policy["regeneration_blocking"],
        "limited_pilot": limited_pilot,
        "partial_pilot": partial_pilot,
        "pilot_limit_frames": int(run_manifest.get("limit_frames", 0) or 0),
        "planned_generative_frames_count": planned_generative_frames,
        "pilot_generated_or_reused_frames": pilot_generated_or_reused,
        "pilot_skipped_due_to_limit_count": int(run_manifest.get("skipped_due_to_limit_count", 0) or 0),
    }
    status = "ready"
    if metrics["continuity_error_count"] or review_policy["render_blocking_count"] or review_policy["regeneration_blocking"]:
        status = "blocked"
    elif partial_pilot:
        status = "pilot_partial"
    elif manual_review or len(regen_tasks) or semantic_flagged or continuity_status == "warn":
        status = "needs_review"
    payload = {"project_id": project.get("project_id"), "created_at": iso_now(), "status": status, "metrics": metrics}
    save_json(json_path, payload)

    lines = [
        "# Production Report",
        "",
        f"Status: **{status}**",
        f"Generated at: {payload['created_at']}",
        "",
        "## Metrics",
    ]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    if regen_tasks:
        lines.extend(["", "## Regeneration / review tasks"])
        for task in regen_tasks[:30]:
            lines.append(f"- {task.get('scene_id')}: {task.get('action')} — {', '.join(task.get('reason', []))}")
    if isinstance(continuity, dict) and continuity.get("warnings"):
        lines.extend(["", "## Continuity warnings"])
        for warning in continuity.get("warnings", [])[:30]:
            lines.append(f"- {warning}")
    if partial_pilot:
        lines.extend(
            [
                "",
                "## Pilot mode",
                f"- limited_pilot: {str(limited_pilot).lower()}",
                f"- partial_pilot: {str(partial_pilot).lower()}",
                f"- planned_generative_frames_count: {planned_generative_frames}",
                f"- pilot_generated_or_reused_frames: {pilot_generated_or_reused}",
                f"- pilot_limit_frames: {metrics['pilot_limit_frames']}",
                f"- pilot_skipped_due_to_limit_count: {metrics['pilot_skipped_due_to_limit_count']}",
            ]
        )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    project.setdefault("reports", {})["production_report_json_path"] = str(json_path)
    project["reports"]["production_report_md_path"] = str(md_path)
    project["reports"]["production_report_status"] = status
    project["current_stage"] = "done"
    project["status"] = status
    if status == "ready" and project.get("render", {}).get("status") == "completed":
        project["status"] = "completed"
    save_project(project_json, project)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
