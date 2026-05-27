import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


def scene_lookup(package: dict) -> dict[str, dict]:
    return {item["scene_id"]: item for item in package.get("items", [])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    visual_shot_plan_path = Path(project["prompts"]["visual_shot_plan_path"])
    output_path = Path(project["prompts"]["shot_prompt_package_path"])
    review_path = Path(project["prompts"]["shot_prompt_review_path"])

    package = load_json(prompt_package_path)
    visual_shot_plan = load_json(visual_shot_plan_path)
    items_by_scene = scene_lookup(package)

    shot_records = []
    review_lines = [
        f"Project: {project['project_id']}",
        f"Quality mode: {visual_shot_plan.get('quality_mode', project['prompts'].get('quality_mode', 'standard'))}",
        "",
    ]

    for shot in visual_shot_plan.get("shots", []):
        shot_id = shot["shot_id"]
        primary_scene_id = shot.get("primary_scene_id") or (shot.get("scene_ids") or [""])[0]
        primary_item = items_by_scene.get(primary_scene_id, {})
        base_prompt = str(primary_item.get("prompt", "")).strip()
        shot_record = {
            "shot_id": shot_id,
            "primary_scene_id": primary_scene_id,
            "scene_ids": shot.get("scene_ids", []),
            "importance": shot.get("importance", "supporting"),
            "generation_mode": shot.get("generation_mode", "unique"),
            "visual_anchor": shot.get("visual_anchor", ""),
            "primary_subject": shot.get("primary_subject") or primary_item.get("primary_subject", ""),
            "what_is_in_frame": primary_item.get("what_is_in_frame", ""),
            "visual_goal": primary_item.get("visual_goal", ""),
            "base_prompt": base_prompt,
            "prompt_strategy": shot.get("prompt_strategy", ""),
            "off_topic_risk": shot.get("off_topic_risk", "unknown"),
            "reference_ids": primary_item.get("reference_ids", []),
        }
        shot_records.append(shot_record)

        review_lines.extend(
            [
                f"Shot {shot_id}",
                f"Primary scene: {primary_scene_id}",
                f"Importance: {shot_record['importance']}",
                f"Generation mode: {shot_record['generation_mode']}",
                f"Scene IDs: {', '.join(shot_record['scene_ids'])}",
                f"Visual anchor: {shot_record['visual_anchor']}",
                f"Primary subject: {shot_record['primary_subject']}",
                f"What is in frame: {shot_record['what_is_in_frame']}",
                f"Prompt strategy: {shot_record['prompt_strategy']}",
                f"Base prompt: {shot_record['base_prompt']}",
                "",
            ]
        )

    payload = {
        "project_id": project["project_id"],
        "quality_mode": visual_shot_plan.get("quality_mode", project["prompts"].get("quality_mode", "standard")),
        "total_shots": len(shot_records),
        "shots": shot_records,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, payload)
    review_path.write_text("\n".join(review_lines).rstrip() + "\n", encoding="utf-8")

    project["prompts"]["shot_prompt_package_path"] = str(output_path)
    project["prompts"]["shot_prompt_review_path"] = str(review_path)
    save_project(project_json, project)

    print(output_path)
    print(review_path)


if __name__ == "__main__":
    main()
