import argparse
import csv
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project


MOVEMENTS = [
    "slow_push_in",
    "pan_left",
    "pan_right",
    "static_tension",
    "diagonal_pan",
    "slow_pull_out",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    source_path = Path(project["prompts"]["final_scene_plan_path"])
    if not source_path.exists():
        source_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(source_path.read_text(encoding="utf-8"))

    json_path = Path(project["motion"]["motion_plan_json_path"])
    csv_path = Path(project["motion"]["motion_plan_csv_path"])
    json_path.parent.mkdir(parents=True, exist_ok=True)

    motion_items = []
    for index, scene in enumerate(scene_plan.get("scenes", []), start=1):
        movement = MOVEMENTS[index % len(MOVEMENTS)]
        motion_id = f"M{index:04d}"
        motion = {
            "motion_id": motion_id,
            "scene_id": scene["scene_id"],
            "image_id": f"{scene['scene_id']}_SELECTED",
            "start_time": scene["start"],
            "end_time": scene["end"],
            "duration": scene["duration"],
            "movement": movement,
            "scale_start": 100,
            "scale_end": 112 if movement == "slow_push_in" else 96 if movement == "slow_pull_out" else 100,
            "x_start": 0,
            "x_end": -3 if movement == "pan_left" else 3 if movement == "pan_right" else 1 if movement == "diagonal_pan" else 0,
            "y_start": 0,
            "y_end": 2 if movement == "diagonal_pan" else 0,
            "rotation_start": 0,
            "rotation_end": 0,
            "transition": "hard_cut",
        }
        motion_items.append(motion)
        scene["motion_id"] = motion_id
        scene["motion_plan"] = motion

    json_path.write_text(json.dumps(motion_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(motion_items[0].keys()) if motion_items else ["motion_id"])
        writer.writeheader()
        for row in motion_items:
            writer.writerow(row)
    source_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    project["motion"]["status"] = "completed"
    project["current_stage"] = "export_prompts"
    save_project(project_json, project)
    print(json_path)


if __name__ == "__main__":
    main()
