import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


def infer_scene_function(index: int, total: int) -> str:
    if index <= 2:
        return "hook"
    if index >= max(1, total - 1):
        return "payoff"
    return "explain"


def infer_visual_role(index: int) -> str:
    roles = ["place", "detail", "human", "process", "consequence"]
    return roles[(index - 1) % len(roles)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_map_path = Path(project["planning"]["scene_map_path"])
    scene_map = load_json(scene_map_path)
    blocks = scene_map.get("sentence_blocks", [])

    semantic_units = []
    total = len(blocks)
    for index, block in enumerate(blocks, start=1):
        semantic_units.append(
            {
                "semantic_unit_id": f"SU{index:04d}",
                "segment_id": block["segment_id"],
                "start": block["start"],
                "end": block["end"],
                "duration": round(float(block["end"]) - float(block["start"]), 6),
                "srt_indices": str(block["segment_id"]),
                "voice_text": block["text"],
                "scene_anchor": block["text"],
                "scene_function": infer_scene_function(index, total),
                "visual_role": infer_visual_role(index),
                "semantic_thesis": block["text"],
            }
        )

    scene_map["semantic_units"] = semantic_units
    save_json(scene_map_path, scene_map)
    project["planning"]["status"] = "scene_map_built"
    project["current_stage"] = "expand_storyboard"
    save_project(project_json, project)
    print(scene_map_path)


if __name__ == "__main__":
    main()
