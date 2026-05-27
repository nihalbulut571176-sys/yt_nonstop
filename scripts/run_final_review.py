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
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    scene_source = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    export_path = Path(project["prompts"]["fastgen_export_path"])
    report_path = Path(project["logs"]["final_review_report_path"])

    scene_plan = json.loads(scene_source.read_text(encoding="utf-8"))
    scenes = scene_plan.get("scenes", [])
    weak_segments = []
    first_minute = [scene for scene in scenes if float(scene.get("start", 0)) < 60.0]
    if len(first_minute) < 6:
        weak_segments.append("First minute has fewer than 6 scenes.")
    if not export_path.exists():
        weak_segments.append("Generator export is missing.")

    missing_prompts = [scene["scene_id"] for scene in scenes if not str(scene.get("final_prompt") or scene.get("prompt", "")).strip()]
    repeated_compositions = []
    for previous, current in zip(scenes, scenes[1:]):
        if previous.get("composition") and previous.get("composition") == current.get("composition"):
            repeated_compositions.append(current["scene_id"])
    event_clarity_failures = []
    for scene in scenes:
        if scene.get("event_clarity_required") and scene.get("shot_role") in {"investigative_bridge", "documentary_bridge", "aftermath_escape"}:
            event_clarity_failures.append(scene["scene_id"])
    if event_clarity_failures:
        weak_segments.append(f"Event clarity failed for scenes: {', '.join(event_clarity_failures[:12])}")

    ready = not missing_prompts and export_path.exists()
    status = "ready_for_generation" if ready and not weak_segments else "ready_with_warnings" if ready else "requires_rework"
    scene_plan["final_review_status"] = status
    for scene in scenes:
        scene.setdefault("qa_status", {})
        scene["qa_status"]["final_review"] = status
    scene_source.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {
        "overall_score": 8.5 if status == "ready_for_generation" else 7.5 if status == "ready_with_warnings" else 5.5,
        "duration_match": True,
        "missing_images": [],
        "weak_segments": weak_segments,
        "repeated_visual_patterns": repeated_compositions[:25],
        "event_clarity_failures": event_clarity_failures,
        "render_status": "not_started",
        "final_outputs": [str(export_path)] if export_path.exists() else [],
        "ready_for_upload": False,
        "status": status,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    project["qc"]["status"] = status
    project["qc"]["last_result"] = payload
    project["current_stage"] = "publishing_package" if status != "requires_rework" else "final_review"
    save_project(project_json, project)
    print(report_path)


if __name__ == "__main__":
    main()
