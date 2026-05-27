import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project


VISUAL_FUNCTIONS = ["hook", "explain", "evidence", "emotion", "transition", "contrast", "pattern_break", "payoff"]
VISUAL_STRATEGIES = [
    "literal_premium",
    "mechanism_view",
    "human_consequence",
    "evidence_wall",
    "scale_contrast",
    "emotional_metaphor",
    "before_after_contrast",
    "tension_detail",
]
COMPOSITIONS = [
    "wide establishing shot",
    "medium documentary shot",
    "close-up detail",
    "macro texture shot",
    "over-the-shoulder investigative shot",
    "reflection shot",
]
LIGHTING = [
    "soft window light mixed with monitor glow",
    "cold ceiling light with reflective glass",
    "warm luxury display lighting contrasted with cold security light",
    "low-key cinematic light with controlled highlights",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    report_path = Path(project["logs"]["visual_direction_report_path"])

    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    report_lines = ["# Visual Direction Report", ""]
    for index, scene in enumerate(scene_plan.get("scenes", []), start=1):
        scene["visual_function"] = scene.get("visual_function") or VISUAL_FUNCTIONS[index % len(VISUAL_FUNCTIONS)]
        scene["visual_strategy"] = scene.get("visual_strategy") or VISUAL_STRATEGIES[index % len(VISUAL_STRATEGIES)]
        scene["visual_idea"] = scene.get("visual_idea") or f"Visualize the meaning of '{scene.get('voice_text', '')}' as a cinematic documentary moment."
        scene["main_subject"] = scene.get("main_subject") or "investigative environment, object, or anonymous human trace"
        scene["environment"] = scene.get("environment") or "documentary environment with layered foreground and background storytelling"
        scene["composition"] = scene.get("composition") or COMPOSITIONS[index % len(COMPOSITIONS)]
        scene["lighting"] = scene.get("lighting") or LIGHTING[index % len(LIGHTING)]
        scene["mood"] = scene.get("mood") or scene.get("viewer_emotion") or "tension"
        scene["visual_reason"] = scene.get("visual_reason") or f"Supports {scene.get('narrative_purpose', 'narrative flow')} without literal duplication."
        scene["visual_goal"] = scene.get("visual_goal") or scene["visual_idea"]
        if scene["duration"] > 5.0 and not scene.get("internal_beats"):
            scene["internal_beats"] = [
                {
                    "beat_id": f"{scene['scene_id']}_B01",
                    "visual_function": scene["visual_function"],
                    "visual_strategy": scene["visual_strategy"],
                    "note": "internal beat placeholder for longer scene",
                }
            ]
        report_lines.append(f"- {scene['scene_id']}: {scene['visual_function']} / {scene['visual_strategy']} / {scene['composition']}")

    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    project["current_stage"] = "continuity_pass"
    save_project(project_json, project)
    print(report_path)


if __name__ == "__main__":
    main()
