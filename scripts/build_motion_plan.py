import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def choose_motion(scene: dict) -> tuple[str, int, int, int, int]:
    visual_function = scene.get("visual_function")
    shot_role = scene.get("shot_role")
    if visual_function in {"hook", "payoff"}:
        return "slow_push_in", 100, 112, 0, -2
    if visual_function == "pattern_break":
        return "diagonal_pan", 101, 107, -2, 3
    if visual_function == "evidence" or shot_role in {"investigative_mechanism", "system_delay", "object_evidence"}:
        return "pan_right", 100, 104, -3, 0
    if shot_role in {"assault_moment", "assault_aftermath", "empty_case_reveal"}:
        return "static_tension", 104, 108, 0, 0
    return "slow_pull_out", 106, 100, 2, 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    selection_manifest_path = Path(project["images"]["selection_manifest_path"])
    selections = {item["scene_id"]: item for item in json.loads(selection_manifest_path.read_text(encoding="utf-8"))}

    motions = []
    for scene in scene_plan["scenes"]:
        selection = selections.get(scene["scene_id"])
        if selection is None:
            raise RuntimeError(f"Missing selection for {scene['scene_id']}")
        movement, scale_start, scale_end, x_end, y_end = choose_motion(scene)
        motion_id = f"M{int(scene['shot_index']):04d}"
        motion = {
            "motion_id": motion_id,
            "scene_id": scene["scene_id"],
            "image_id": selection["selected_image_id"],
            "image_path": selection["selected_image_path"],
            "start_time": scene["start"],
            "end_time": scene["end"],
            "duration": scene["duration"],
            "movement": movement,
            "scale_start": scale_start,
            "scale_end": scale_end,
            "x_start": 0,
            "x_end": x_end,
            "y_start": 0,
            "y_end": y_end,
            "rotation_start": 0,
            "rotation_end": 0,
            "transition": "cut_on_contrast" if scene.get("pattern_break_score", 0) >= 8.5 else "hard_cut",
        }
        motions.append(motion)
        scene["motion_id"] = motion_id
        scene["selected_image_path"] = selection["selected_image_path"]
        scene["selected_image_id"] = selection["selected_image_id"]

    motion_dir = Path(project["meta"]["project_root"]) / "motion"
    motion_dir.mkdir(parents=True, exist_ok=True)
    motion_plan_path = motion_dir / "motion_plan.json"
    motion_plan_path.write_text(json.dumps(motions, ensure_ascii=False, indent=2), encoding="utf-8")
    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    project["render"]["motion_plan_path"] = str(motion_plan_path)
    project["render"]["status"] = "motion_planned"
    project["current_stage"] = "timeline"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(motion_plan_path)


if __name__ == "__main__":
    main()
