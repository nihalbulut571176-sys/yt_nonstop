import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


def combine_prompt(base_prompt: str, variation_note: str, generation_mode: str, source_shot_id: str) -> str:
    prompt = str(base_prompt or "").strip()
    variation_note = str(variation_note or "").strip()
    if variation_note:
        prompt = f"{prompt} Variation note: {variation_note}.".strip()
    if generation_mode == "reused":
        prompt = f"{prompt} Keep the same visual motif and documentary world as {source_shot_id}.".strip()
    elif generation_mode == "derived":
        prompt = f"{prompt} Keep continuity with {source_shot_id} while applying only the described framing variation.".strip()
    return prompt.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--output-json", help="Optional explicit path for scene-level llm prompt drafts output.")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    visual_shot_plan_path = Path(project["prompts"]["visual_shot_plan_path"])
    shot_prompt_package_path = Path(project["prompts"]["shot_prompt_package_path"])
    output_path = Path(args.output_json).resolve() if args.output_json else Path(project["prompts"]["llm_prompt_drafts_path"])

    prompt_package = load_json(prompt_package_path)
    visual_shot_plan = load_json(visual_shot_plan_path)
    shot_prompt_package = load_json(shot_prompt_package_path)

    items_by_scene = {item["scene_id"]: item for item in prompt_package.get("items", [])}
    shots_by_id = {shot["shot_id"]: shot for shot in shot_prompt_package.get("shots", [])}

    drafts = []
    for scene_id, mapping in visual_shot_plan.get("scene_to_shot", {}).items():
        item = items_by_scene.get(scene_id)
        if not item:
            continue
        shot_id = mapping["shot_id"]
        source_shot_id = mapping.get("source_shot_id", shot_id) or shot_id
        shot = shots_by_id.get(shot_id) or shots_by_id.get(source_shot_id)
        if not shot:
            continue
        final_prompt = combine_prompt(
            base_prompt=str(shot.get("base_prompt", "")).strip(),
            variation_note=mapping.get("variation_note", ""),
            generation_mode=mapping.get("generation_mode", shot.get("generation_mode", "unique")),
            source_shot_id=source_shot_id,
        )
        drafts.append(
            {
                "scene_id": scene_id,
                "visual_goal": shot.get("visual_goal", item.get("visual_goal", "")),
                "final_prompt": final_prompt,
                "shot_id": shot_id,
                "source_shot_id": source_shot_id,
                "scene_importance": shot.get("importance", item.get("scene_importance", "")),
                "generation_mode": mapping.get("generation_mode", shot.get("generation_mode", "unique")),
                "variation_note": mapping.get("variation_note", ""),
                "primary_subject": shot.get("primary_subject", item.get("primary_subject", "")),
                "what_is_in_frame": shot.get("what_is_in_frame", item.get("what_is_in_frame", "")),
                "camera": item.get("camera", ""),
                "composition": item.get("composition", ""),
                "lighting": item.get("lighting", ""),
                "mood": item.get("mood", ""),
                "continuity_notes": f"Expanded from {shot_id} via {mapping.get('generation_mode', 'unique')}",
                "prompt_origin": "shot_prompt_package",
            }
        )

    save_json(output_path, drafts)
    project["prompts"]["llm_prompt_drafts_path"] = str(output_path)
    save_project(project_json, project)

    print(output_path)


if __name__ == "__main__":
    main()
