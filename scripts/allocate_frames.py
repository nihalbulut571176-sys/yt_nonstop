import argparse
import json
from pathlib import Path

from build_project_scene_plan import build_scene_plan
from pipeline_contracts import build_semantic_unit_id
from project_pipeline_utils import iso_now, load_json, load_project, save_project


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_map = load_json(Path(project["planning"]["scene_map_path"]))
    sentence_blocks = scene_map.get("sentence_blocks", [])
    max_duration = float(project["scene_plan"]["max_still_duration_seconds"])
    scenes, long_segments = build_scene_plan(sentence_blocks, max_duration)

    for scene in scenes:
        scene["semantic_unit_id"] = build_semantic_unit_id(int(scene["source_segment_id"]))
        scene["srt_indices"] = str(scene["source_segment_id"])

    scene_plan = {
        "project_id": project["project_id"],
        "schema_version": project["schema_version"],
        "created_at": iso_now(),
        "source_srt_path": scene_map["source_srt_path"],
        "canonical_timing_source": "cleaned.srt" if "cleaned.srt" in scene_map["source_srt_path"] else "raw_whisper.srt",
        "max_still_duration_seconds": max_duration,
        "timing_locked": False,
        "scene_qa_status": "pending",
        "prompt_qa_status": "pending",
        "final_review_status": "pending",
        "scene_count": len(scenes),
        "scenes": scenes,
    }

    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan_path.parent.mkdir(parents=True, exist_ok=True)
    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    long_segment_report_path = Path(project["scene_plan"]["long_segment_report_path"])
    long_segment_report_path.write_text(
        json.dumps(
            {
                "max_duration_seconds": max_duration,
                "original_segments": len(sentence_blocks),
                "long_segments": len(long_segments),
                "final_scene_count": len(scenes),
                "segments": long_segments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    project["scene_plan"]["status"] = "completed"
    project["scene_plan"]["scene_count"] = len(scenes)
    project["scene_plan"]["original_segment_count"] = len(sentence_blocks)
    project["current_stage"] = "build_frame_briefs"
    save_project(project_json, project)
    print(scene_plan_path)


if __name__ == "__main__":
    main()
