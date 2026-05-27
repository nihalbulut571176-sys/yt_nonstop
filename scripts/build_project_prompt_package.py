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
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))

    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    prompt_review_path = Path(project["prompts"]["prompt_review_path"])
    prompt_package_path.parent.mkdir(parents=True, exist_ok=True)

    items = []
    review_blocks = []
    for scene in scene_plan.get("scenes", []):
        item = {
            "scene_id": scene["scene_id"],
            "shot_index": scene["shot_index"],
            "source_segment_id": scene["source_segment_id"],
            "part_index": scene["part_index"],
            "parts_total": scene["parts_total"],
            "start": scene["start"],
            "end": scene["end"],
            "duration": scene["duration"],
            "voice_text": scene["voice_text"],
            "scene_summary": scene.get("scene_summary", ""),
            "scene_meaning": scene.get("scene_meaning", ""),
            "narrative_purpose": scene.get("narrative_purpose", ""),
            "viewer_emotion": scene.get("viewer_emotion", ""),
            "tension_level": scene.get("tension_level", 0),
            "curiosity_hook": scene.get("curiosity_hook", ""),
            "retention_risk": scene.get("retention_risk", ""),
            "visual_need": scene.get("visual_need", ""),
            "visual_function": scene.get("visual_function", ""),
            "visual_strategy": scene.get("visual_strategy", ""),
            "visual_idea": scene.get("visual_idea", ""),
            "main_subject": scene.get("main_subject", ""),
            "environment": scene.get("environment", ""),
            "visual_goal": scene.get("visual_goal", ""),
            "scene_importance": scene.get("scene_importance", ""),
            "event_clarity_required": scene.get("event_clarity_required", False),
            "event_type": scene.get("event_type", ""),
            "event_priority_reason": scene.get("event_priority_reason", ""),
            "shot_id": scene.get("shot_id", ""),
            "source_shot_id": scene.get("source_shot_id", ""),
            "generation_mode": scene.get("generation_mode", ""),
            "variation_note": scene.get("variation_note", ""),
            "shot_role": scene.get("shot_role", ""),
            "primary_subject": scene.get("primary_subject", ""),
            "secondary_subjects": scene.get("secondary_subjects", []),
            "what_is_in_frame": scene.get("what_is_in_frame", ""),
            "camera": scene.get("camera", ""),
            "composition": scene.get("composition", ""),
            "lighting": scene.get("lighting", ""),
            "mood": scene.get("mood", ""),
            "continuity_notes": scene.get("continuity_notes", ""),
            "negative_prompt": scene.get("negative_prompt", ""),
            "reference_ids": scene.get("reference_ids", []),
            "reference_mode": scene.get("reference_mode", "none"),
            "draft_prompt": scene.get("draft_prompt", ""),
            "final_prompt": scene.get("final_prompt", ""),
            "prompt": scene.get("final_prompt") or scene.get("prompt", ""),
            "quality_target": scene.get("quality_target", 8.5),
            "internal_beats": scene.get("internal_beats", []),
            "status": "pending_prompt",
            "notes": [],
        }
        items.append(item)

        review_blocks.append(
            "\n".join(
                [
                    f"Scene {scene['shot_index']} ({scene['scene_id']})",
                    f"Timing: {scene['start']:.3f}-{scene['end']:.3f}s",
                    f"Duration: {scene['duration']:.3f}s",
                    f"Voice text: {scene['voice_text']}",
                    f"Narrative purpose: {scene.get('narrative_purpose', '')}",
                    f"Viewer emotion: {scene.get('viewer_emotion', '')}",
                    f"Visual function: {scene.get('visual_function', '')}",
                    f"Visual strategy: {scene.get('visual_strategy', '')}",
                    f"Visual idea: {scene.get('visual_idea', '')}",
                    f"Reference IDs: {', '.join(scene.get('reference_ids', [])) if scene.get('reference_ids') else 'none'}",
                    f"Scene importance: {scene.get('scene_importance', '')}",
                    "Prompt:",
                    scene.get("final_prompt") or scene.get("prompt", ""),
                ]
            ).rstrip()
        )

    package = {
        "project_id": project["project_id"],
        "profile_id": project["profile_id"],
        "schema_version": project["schema_version"],
        "source_language": project["meta"].get("language", "auto"),
        "prompt_language": project["prompts"]["prompt_language"],
        "style_preset": project["prompts"]["style_preset"],
        "global_style_summary": project["prompts"].get("global_style_summary"),
        "canonical_scene_plan_path": str(scene_plan_path),
        "scene_count": len(items),
        "items": items,
    }
    prompt_package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_review_path.write_text("\n\n".join(review_blocks) + "\n", encoding="utf-8")

    project["prompts"]["status"] = "package_built"
    project["current_stage"] = "scene_context_pack"
    save_project(project_json, project)

    print(prompt_package_path)
    print(prompt_review_path)


if __name__ == "__main__":
    main()
