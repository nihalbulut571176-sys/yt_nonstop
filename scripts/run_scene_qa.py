import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    report_path = Path(project["logs"]["scene_qa_report_path"])
    json_path = Path(project["logs"]["scene_qa_json_path"])

    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    scenes = scene_plan.get("scenes", [])
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    previous_end = -1.0

    for scene in scenes:
        scene_id = scene.get("scene_id")
        if not scene_id:
            errors.append("Scene without scene_id found")
            continue
        if scene_id in seen_ids:
            errors.append(f"Duplicate scene_id: {scene_id}")
        seen_ids.add(scene_id)
        start = float(scene.get("start", 0) or 0)
        end = float(scene.get("end", 0) or 0)
        duration = float(scene.get("duration", 0) or 0)
        if end <= start:
            errors.append(f"{scene_id} has invalid time range")
        if abs((end - start) - duration) > 0.05:
            errors.append(f"{scene_id} duration does not match start/end")
        if previous_end > start + 0.02:
            warnings.append(f"{scene_id} overlaps previous scene")
        previous_end = max(previous_end, end)
        if not str(scene.get("voice_text", "")).strip():
            errors.append(f"{scene_id} has empty voice_text")
        if duration > float(project["scene_plan"]["max_still_duration_seconds"]) + 0.01:
            warnings.append(f"{scene_id} exceeds max still duration and should have internal beats")

    status = "approved" if not errors else "rejected"
    scene_plan["timing_locked"] = not errors
    scene_plan["scene_qa_status"] = status
    for scene in scenes:
        scene.setdefault("qa_status", {})
        scene["qa_status"]["scene_qa"] = "approved" if not errors else "rejected"
    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {"status": status, "errors": errors, "warnings": warnings, "scene_count": len(scenes)}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_lines = [
        "# Scene QA Report",
        "",
        f"Status: {status}",
        f"Scene count: {len(scenes)}",
        "",
        "## Errors",
        *(errors or ["- none"]),
        "",
        "## Warnings",
        *(warnings or ["- none"]),
    ]
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    if errors:
        project["scene_plan"]["status"] = "failed"
    else:
        project["scene_plan"]["status"] = "approved"
        project["current_stage"] = "narrative_enrichment"
    save_project(project_json, project)

    print(report_path)


if __name__ == "__main__":
    main()
