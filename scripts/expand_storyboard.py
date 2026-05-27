import argparse
from pathlib import Path

from pipeline_contracts import build_storyboard_id
from project_pipeline_utils import load_json, load_project, save_json, save_project


def storyboard_record(unit: dict, index: int, total: int) -> dict:
    function = unit.get("scene_function", "explain")
    role = unit.get("visual_role", "process")
    transition = "hard pivot into the next beat" if index < total else "close the current sequence cleanly"
    return {
        "storyboard_id": build_storyboard_id(index),
        "semantic_unit_id": unit["semantic_unit_id"],
        "segment_id": unit["segment_id"],
        "scene_id": f"scene_{index:04d}",
        "scene_function": function,
        "shot_function": function,
        "visual_role": role,
        "on_screen_action": f"Show a documentary moment that makes '{unit['voice_text']}' visually legible without readable text.",
        "attention_flow": "foreground clue -> main subject -> background confirmation",
        "composition_progression": "start with a clear anchor, then reveal context depth",
        "internal_montage": "single-frame still designed for documentary montage continuity",
        "visual_dramaturgy": f"Use the frame as a {function} beat with {role} emphasis.",
        "scene_risks_and_prohibitions": ["no readable text", "no logos", "no fake UI", "no stock-photo look"],
        "transition_to_next": transition,
        "camera_storyboard": "restrained documentary framing with one clear narrative priority",
        "screen_action": unit["voice_text"],
        "source_stage": "expand_storyboard",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_map = load_json(Path(project["planning"]["scene_map_path"]))
    semantic_units = scene_map.get("semantic_units", [])

    storyboard = {
        "project_id": project["project_id"],
        "storyboard_required": bool(project["workflow"].get("is_sequence", True)),
        "items": [storyboard_record(unit, index, len(semantic_units)) for index, unit in enumerate(semantic_units, start=1)],
    }

    storyboard_path = Path(project["planning"]["storyboard_path"])
    save_json(storyboard_path, storyboard)
    project["planning"]["status"] = "storyboard_expanded"
    project["current_stage"] = "allocate_frames"
    save_project(project_json, project)
    print(storyboard_path)


if __name__ == "__main__":
    main()
