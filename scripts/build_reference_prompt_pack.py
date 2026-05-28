import argparse
from pathlib import Path

from build_project_continuity_bible import (
    generic_documentary_continuity,
    heist_continuity,
    infer_theme,
    read_story_text,
    wildlife_continuity,
)
from build_subject_registry import policy_for_subject, subject_type_for
from pipeline_contracts import has_cyrillic
from project_pipeline_utils import load_json, load_project, save_json, save_project


NEGATIVE_PROMPT = (
    "glamour fashion campaign, beauty retouch, stylized fantasy, cartoon, plastic skin, celebrity likeness, "
    "extra fingers, warped anatomy, hard shadow mask, logo, watermark, lettering, subtitles, badge text"
)


def infer_display_name(profile: dict, subject_id: str) -> str:
    return str(profile.get("display_name") or profile.get("name") or profile.get("role") or subject_id).strip()


def clean_prompt_text(value: str) -> str:
    return " ".join(str(value or "").split())


def build_reference_prompt(display_name: str, continuity_prompt: str) -> str:
    continuity_bits = clean_prompt_text(continuity_prompt)
    prompt = (
        "Premium cinematic documentary identity sheet, realistic photography, single wide 16:9 frame. "
        f"Show the same recurring subject {display_name} four times inside one horizontal composition, left to right: "
        "front-facing chest-up portrait, close-up of hands and sleeves, three-quarter side portrait, full-body wardrobe view. "
        f"Continuity description: {continuity_bits}. "
        "Neutral unobtrusive studio backdrop, even realistic lighting, natural skin texture, grounded posture, "
        "clear wardrobe readability, identity consistency across all four views, documentary-safe realism, "
        "no lettering, no logos, no panel labels, no collage text, no contact-sheet numbers."
    )
    return clean_prompt_text(prompt)


def build_prompt_items(continuity: dict, character_root: Path) -> list[dict]:
    items: list[dict] = []
    for profile in continuity.get("character_profiles", []):
        subject_id = str(profile.get("entity_id", "")).strip()
        if not subject_id:
            continue
        policy = policy_for_subject(subject_id, profile)
        subject_type = subject_type_for(subject_id, profile)
        if policy == "never" or subject_type != "person":
            continue

        display_name = infer_display_name(profile, subject_id)
        continuity_prompt = str(profile.get("profile") or profile.get("role") or "").strip()
        relative_output_path = Path(subject_id) / "identity_sheet.png"
        absolute_output_path = character_root / relative_output_path
        items.append(
            {
                "reference_asset_id": f"ref_{subject_id}_identity_sheet",
                "subject_id": subject_id,
                "display_name": display_name,
                "subject_type": subject_type,
                "reference_policy": policy,
                "shot_kind": "identity_sheet",
                "usage": "identity_sheet",
                "strength": "strict",
                "relative_output_path": str(relative_output_path).replace("\\", "/"),
                "output_path": str(absolute_output_path),
                "prompt": build_reference_prompt(display_name, continuity_prompt),
                "negative_prompt": NEGATIVE_PROMPT,
                "continuity_prompt": continuity_prompt,
            }
        )
    return items


def continuity_with_fallback(project: dict, continuity: dict) -> dict:
    if continuity.get("character_profiles"):
        return continuity

    scene_ids: list[str] = []
    storyboard_path = Path(project["planning"].get("storyboard_frames_path", ""))
    scene_plan_path = Path(project["scene_plan"].get("scene_plan_path", ""))
    if storyboard_path.exists():
        payload = load_json(storyboard_path)
        scene_ids = [str(frame.get("scene_id", "")).strip() for frame in payload.get("frames", []) if str(frame.get("scene_id", "")).strip()]
    elif scene_plan_path.exists():
        payload = load_json(scene_plan_path)
        scene_ids = [str(scene.get("scene_id", "")).strip() for scene in payload.get("scenes", []) if str(scene.get("scene_id", "")).strip()]

    story_text = read_story_text(project)
    theme = infer_theme(project, story_text)
    unique_scene_ids = list(dict.fromkeys(scene_ids))
    if theme == "luxury_jewel_heist_documentary":
        return heist_continuity(unique_scene_ids)
    if theme == "wildlife_documentary":
        return wildlife_continuity(unique_scene_ids)
    return generic_documentary_continuity(unique_scene_ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    continuity_path = Path(project["planning"]["continuity_map_json_path"])
    continuity = load_json(continuity_path) if continuity_path.exists() else {}
    continuity = continuity_with_fallback(project, continuity)
    character_root = Path(project["assets"]["character_references_root"])
    pack_path = Path(project["prompts"]["reference_prompt_pack_path"])

    items = build_prompt_items(continuity, character_root)
    payload = {
        "project_id": project["project_id"],
        "project_root": project["meta"]["project_root"],
        "items": items,
    }
    save_json(pack_path, payload)

    report_lines = [
        "# Reference Prompt Pack",
        "",
        f"Items: {len(items)}",
        f"Output: {pack_path}",
    ]
    cyrillic_subjects = sorted({item["subject_id"] for item in items if has_cyrillic(item["prompt"])})
    if cyrillic_subjects:
        report_lines.extend(["", "Cyrillic detected in prompts:", *[f"- {subject_id}" for subject_id in cyrillic_subjects]])
    report_path = Path(project["logs"]["generation_report_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    project["planning"]["status"] = "reference_prompt_pack_built"
    project["current_stage"] = "generate_reference_images"
    save_project(project_json, project)
    print(pack_path)


if __name__ == "__main__":
    main()
