import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


def build_safe_prompt(item: dict) -> str:
    primary_subject = str(item.get("primary_subject") or "wolves").strip()
    camera = str(item.get("camera") or "balanced documentary shot").strip()
    lighting = str(item.get("lighting") or "natural atmospheric light").strip()
    mood = str(item.get("mood") or "restrained, cinematic, observant").strip()
    return (
        "Ultra-realistic cinematic documentary still, natural light, rich organic textures, realistic anatomy, "
        f"atmospheric depth, 16:9 composition, no text. Documentary still of {primary_subject} in a calm natural "
        "forest or meadow environment, showing non-graphic wildlife behavior, readable body language, and clear "
        f"environmental context. {camera}, {lighting}, mood: {mood}. Avoid blood, injury, collision, carcass, "
        "weapons, attack imagery, meat, or graphic conflict. No text, no watermark, no logo."
    )


def build_safe_frame_description(item: dict) -> str:
    primary_subject = str(item.get("primary_subject") or "wolf family group").strip()
    return (
        f"A grounded documentary image centered on {primary_subject} in a calm forest clearing or meadow edge, "
        "showing gentle non-graphic family or social behavior, readable body language, and a safe natural environment."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--indices-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    indices = set(load_json(Path(args.indices_json).resolve()))

    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    package = load_json(prompt_package_path)

    changed = 0
    for prompt_index, item in enumerate(package.get("items", []), start=1):
        if prompt_index not in indices:
            continue
        item["primary_subject"] = "wolf family group"
        item["visual_goal"] = "show calm, non-graphic wolf family or social behavior in a grounded wildlife-documentary moment"
        item["what_is_in_frame"] = build_safe_frame_description(item)
        item["prompt"] = build_safe_prompt(item)
        item["negative_prompt"] = (
            "blood, regurgitation, carcass, meat, injury, collision, attack, violence, weapons, text, watermark, logo"
        )
        notes = list(item.get("notes", []))
        notes.append("Prompt softened automatically after policy-related image failure")
        item["notes"] = notes
        changed += 1

    save_json(prompt_package_path, package)
    project["prompts"]["status"] = "drafted"
    save_project(project_json, project)

    print(json.dumps({"updated_prompts": changed, "indices": sorted(indices)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
