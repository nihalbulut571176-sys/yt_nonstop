import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project
from pipeline_contracts import write_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    frame_briefs = load_json(Path(project["planning"]["frame_briefs_json_path"]))
    scene_source = Path(project["prompts"]["final_scene_plan_path"])
    if not scene_source.exists():
        scene_source = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = load_json(scene_source)
    scenes_by_frame = {scene.get("frame_id"): scene for scene in scene_plan.get("scenes", [])}

    rows = []
    for frame_brief in frame_briefs:
        scene = scenes_by_frame.get(frame_brief["frame_id"], {})
        rows.append(
            {
                "frame_id": frame_brief["frame_id"],
                "asset_image_path": scene.get("still_image_path"),
                "asset_video_path": scene.get("video_path"),
                "timeline_in": frame_brief["timeline_in"],
                "timeline_out": frame_brief["timeline_out"],
                "duration_sec": frame_brief["duration_sec"],
                "segment_id": frame_brief["segment_id"],
                "srt_indices": frame_brief["srt_indices"],
                "srt_text": frame_brief["srt_text"],
                "screen_action": frame_brief["screen_action"],
                "motion_note": scene.get("motion_prompt") or frame_brief.get("motion_treatment"),
            }
        )

    json_path = Path(project["exports"]["montage_timing_map_json_path"])
    csv_path = Path(project["exports"]["montage_timing_map_csv_path"])
    xlsx_path = Path(project["exports"]["montage_timing_map_xlsx_path"])
    save_json(json_path, rows)
    write_csv(csv_path, rows)
    try:
        import openpyxl  # type: ignore

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "montage_timing_map"
        if rows:
            headers = list(rows[0].keys())
            sheet.append(headers)
            for row in rows:
                sheet.append([json.dumps(row[key], ensure_ascii=False) if isinstance(row[key], (dict, list)) else row[key] for key in headers])
        workbook.save(xlsx_path)
    except Exception:
        pass

    project["exports"]["status"] = "montage_map_ready"
    project["current_stage"] = "export_generation_batches"
    save_project(project_json, project)
    print(json_path)


if __name__ == "__main__":
    main()
