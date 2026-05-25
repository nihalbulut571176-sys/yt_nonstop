import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project


PURPOSES = ["hook", "explain", "evidence", "emotion", "transition", "contrast", "pattern_break", "payoff"]
EMOTIONS = ["curiosity", "unease", "pressure", "discovery", "scale", "tension", "reflection", "payoff"]


def pick(items: list[str], index: int) -> str:
    return items[index % len(items)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    narrative_map_path = scene_plan_path.parent / "narrative_map.json"
    report_path = Path(project["logs"]["narrative_editor_report_path"])

    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    narrative_map = []
    for index, scene in enumerate(scene_plan.get("scenes", []), start=1):
        purpose = "hook" if index <= 3 else "payoff" if index > max(1, len(scene_plan["scenes"]) - 3) else pick(PURPOSES[1:-1], index)
        emotion = "tension / curiosity" if index <= 8 else pick(EMOTIONS, index)
        scene["scene_meaning"] = scene.get("scene_meaning") or scene.get("voice_text", "")
        scene["narrative_purpose"] = scene.get("narrative_purpose") or purpose
        scene["viewer_emotion"] = scene.get("viewer_emotion") or emotion
        scene["tension_level"] = scene.get("tension_level") or min(10, 6 + (1 if index <= 8 else 0))
        scene["curiosity_hook"] = scene.get("curiosity_hook") or ("open investigative question" if index <= 8 else "continue narrative progression")
        scene["information_density"] = scene.get("information_density") or ("high" if len(scene.get("voice_text", "")) > 140 else "medium")
        scene["retention_risk"] = scene.get("retention_risk") or ("high_priority_first_minute" if scene["start"] < 60 else "normal")
        scene["visual_need"] = scene.get("visual_need") or ("pattern_break" if index % 6 == 0 else "support")
        narrative_map.append(
            {
                "scene_id": scene["scene_id"],
                "narrative_purpose": scene["narrative_purpose"],
                "viewer_emotion": scene["viewer_emotion"],
                "retention_risk": scene["retention_risk"],
            }
        )

    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    narrative_map_path.write_text(json.dumps(narrative_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(
        "# Narrative Editor Report\n\n"
        f"Scenes enriched: {len(narrative_map)}\n"
        f"First-minute priority scenes: {sum(1 for scene in scene_plan['scenes'] if scene['start'] < 60)}\n",
        encoding="utf-8",
    )

    project["current_stage"] = "style_bible"
    save_project(project_json, project)
    print(narrative_map_path)


if __name__ == "__main__":
    main()
