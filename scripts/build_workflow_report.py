import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project
from validate_project import validate_quality_assurance


def classify_retry_actions(locked_rows: list[dict], qa_report: dict) -> list[dict]:
    actions: list[dict] = []
    frame_level_targets = [row["frame_id"] for row in locked_rows if row.get("generation_lock_status") == "failed"]
    if frame_level_targets:
        actions.append(
            {
                "scope": "frame",
                "reason": "generation_lock_failed",
                "targets": frame_level_targets,
            }
        )

    scene_targets = set()
    project_targets = []
    for message in qa_report.get("warnings", []) + qa_report.get("errors", []):
        if "scene_monotony" in message:
            scene_targets.add(message.split(": ", 1)[-1].split(" ", 1)[0])
        if any(marker in message for marker in ("timing_gap", "timing_overlap", "storyboard", "srt_coverage")):
            project_targets.append(message)

    if scene_targets:
        actions.append(
            {
                "scope": "scene",
                "reason": "scene_monotony",
                "targets": sorted(scene_targets),
            }
        )
    if project_targets:
        actions.append(
            {
                "scope": "project",
                "reason": "structural_issue",
                "targets": project_targets,
            }
        )
    return actions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    locked_rows = load_json(Path(project["prompts"]["generation_locked_json_path"]))
    frame_briefs = load_json(Path(project["planning"]["frame_briefs_json_path"]))
    qa_errors, qa_warnings = validate_quality_assurance(project)
    continuity_path = Path(project["planning"]["continuity_map_json_path"])
    montage_path = Path(project["exports"]["montage_timing_map_json_path"])
    export_path = Path(project["prompts"]["fastgen_export_path"])
    report_path = Path(project["logs"]["workflow_report_path"])
    report_json_path = Path(project["logs"]["workflow_report_json_path"])

    locked = sum(1 for row in locked_rows if row.get("generation_lock_status") == "locked")
    locked_with_warnings = sum(1 for row in locked_rows if row.get("generation_lock_status") == "locked_with_warnings")
    failed = sum(1 for row in locked_rows if row.get("generation_lock_status") == "failed")
    continuity_present = continuity_path.exists()
    continuity_fallback_frames = [row["frame_id"] for row in locked_rows if "continuity_fallback" in row.get("validation_flags", [])]

    qa_report = {
        "status": "failed" if qa_errors else "passed",
        "errors": qa_errors,
        "warnings": qa_warnings,
    }

    payload = {
        "project_id": project["project_id"],
        "frame_brief_count": len(frame_briefs),
        "locked_count": locked,
        "locked_with_warnings_count": locked_with_warnings,
        "failed_count": failed,
        "continuity_map_present": continuity_present,
        "continuity_fallback_count": len(continuity_fallback_frames),
        "montage_map_path": str(montage_path),
        "generator_ready_path": str(export_path),
        "qa_status": qa_report["status"],
        "qa_errors": qa_report["errors"],
        "qa_warnings": qa_report["warnings"],
        "retry_actions": classify_retry_actions(locked_rows, qa_report),
    }

    report_lines = [
        "# Workflow Report",
        "",
        f"Frame briefs: {payload['frame_brief_count']}",
        f"Locked frames: {payload['locked_count']}",
        f"Locked with warnings: {payload['locked_with_warnings_count']}",
        f"Failed frames: {payload['failed_count']}",
        f"Continuity map present: {payload['continuity_map_present']}",
        f"Continuity fallback frames: {payload['continuity_fallback_count']}",
        f"Montage map: {payload['montage_map_path']}",
        f"Generator-ready prompts: {payload['generator_ready_path']}",
        "",
        "## Retry Actions",
    ]
    if payload["retry_actions"]:
        report_lines.extend(
            f"- {item['scope']}: {item['reason']} -> {', '.join(str(target) for target in item['targets'])}"
            for item in payload["retry_actions"]
        )
    else:
        report_lines.append("- none")

    report_lines.extend(["", "## QA Warnings"])
    report_lines.extend([f"- {warning}" for warning in payload["qa_warnings"]] or ["- none"])
    report_lines.extend(["", "## QA Errors"])
    report_lines.extend([f"- {error}" for error in payload["qa_errors"]] or ["- none"])

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    save_json(report_json_path, payload)

    project["qc"]["status"] = qa_report.get("status", project["qc"].get("status"))
    project["current_stage"] = "motion_plan"
    save_project(project_json, project)
    print(report_json_path)


if __name__ == "__main__":
    main()
