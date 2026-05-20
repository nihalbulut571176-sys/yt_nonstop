import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    prompts_dir = Path(project["meta"]["project_root"]) / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    prompt_review_path = Path(project["prompts"]["prompt_review_path"])

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
            "visual_goal": scene.get("visual_goal", ""),
            "reference_ids": scene.get("reference_ids", []),
            "reference_mode": scene.get("reference_mode", "none"),
            "prompt": scene.get("prompt", ""),
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
                    f"Reference IDs: {', '.join(scene.get('reference_ids', [])) if scene.get('reference_ids') else 'none'}",
                    "Visual goal:",
                    scene.get("visual_goal", ""),
                    "Prompt:",
                    scene.get("prompt", ""),
                ]
            ).rstrip()
        )

    package = {
        "project_id": project["project_id"],
        "profile_id": project["profile_id"],
        "schema_version": project["schema_version"],
        "prompt_language": project["prompts"]["prompt_language"],
        "style_preset": project["prompts"]["style_preset"],
        "scene_count": len(items),
        "items": items,
    }
    prompt_package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_review_path.write_text("\n\n".join(review_blocks) + "\n", encoding="utf-8")

    project["prompts"]["status"] = "package_built"
    project["current_stage"] = "publishing_drafts"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(prompt_package_path)
    print(prompt_review_path)


if __name__ == "__main__":
    main()
