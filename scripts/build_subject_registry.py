import argparse
from pathlib import Path

from build_project_continuity_bible import (
    generic_documentary_continuity,
    heist_continuity,
    infer_theme,
    read_story_text,
    wildlife_continuity,
)
from pipeline_contracts import ReferenceAsset, SubjectProfile
from project_pipeline_utils import load_json, load_project, save_json, save_project


def policy_for_subject(entity_id: str, profile: dict) -> str:
    lowered = f"{entity_id} {profile.get('profile', '')}".lower()
    if any(token in lowered for token in ("operator", "guard", "worker", "cashier", "customer", "shopper", "farmer", "producer")):
        return "required"
    if any(token in lowered for token in ("crowd", "silhouette", "background", "hands")):
        return "never"
    if "anonymous" in lowered:
        return "optional"
    return "optional"


def subject_type_for(entity_id: str, profile: dict) -> str:
    lowered = f"{entity_id} {profile.get('profile', '')}".lower()
    if "hand" in lowered:
        return "hands"
    if "crowd" in lowered:
        return "crowd"
    if "silhouette" in lowered:
        return "silhouette"
    return "person"


def infer_assets_for_subject(subject_id: str, character_root: Path) -> list[ReferenceAsset]:
    subject_dir = character_root / subject_id
    assets = []
    if not subject_dir.exists():
        return assets
    identity_sheet_candidates = [path for path in sorted(subject_dir.iterdir()) if path.is_file() and "identity_sheet" in path.stem.lower()]
    if identity_sheet_candidates:
        path = identity_sheet_candidates[0]
        return [
            ReferenceAsset(
                reference_asset_id=f"ref_{subject_id}_{path.stem.lower()}",
                subject_id=subject_id,
                path=str(path),
                usage="identity_sheet",
                strength="strict",
                allowed_segments=[],
            )
        ]
    usage_by_name = {
        "front": ("face", "medium"),
        "side": ("body", "medium"),
        "wardrobe": ("wardrobe", "strict"),
        "hands": ("hands", "loose"),
        "pose": ("pose", "loose"),
        "portrait": ("face", "strict"),
    }
    for path in sorted(subject_dir.iterdir()):
        if not path.is_file():
            continue
        stem = path.stem.lower()
        usage, strength = next((value for key, value in usage_by_name.items() if key in stem), ("body", "medium"))
        assets.append(
            ReferenceAsset(
                reference_asset_id=f"ref_{subject_id}_{path.stem.lower()}",
                subject_id=subject_id,
                path=str(path),
                usage=usage,
                strength=strength,
                allowed_segments=[],
            )
        )
    return assets


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

    profiles = []
    assets = []
    for profile in continuity.get("character_profiles", []):
        subject_id = str(profile.get("entity_id", "")).strip()
        if not subject_id:
            continue
        subject_assets = infer_assets_for_subject(subject_id, character_root)
        subject_profile = SubjectProfile(
            subject_id=subject_id,
            display_name=str(profile.get("display_name") or profile.get("name") or subject_id),
            subject_type=subject_type_for(subject_id, profile),
            narrative_role=str(profile.get("profile") or profile.get("role") or "recurring documentary subject"),
            visual_markers=list(profile.get("visual_markers", [])),
            reference_policy=policy_for_subject(subject_id, profile),
            reference_asset_ids=[asset.reference_asset_id for asset in subject_assets],
            continuity_prompt=str(profile.get("profile") or ""),
            forbidden_variation=[
                "do not change age drastically",
                "do not change wardrobe color without reason",
                "do not turn into a different person between shots",
            ],
        )
        profiles.append(subject_profile.__dict__)
        assets.extend(asset.__dict__ for asset in subject_assets)

    subject_registry_path = Path(project["prompts"]["subject_registry_path"])
    entity_registry_path = Path(project["prompts"]["entity_registry_path"])
    ref_assets_path = Path(project["prompts"]["reference_assets_manifest_path"])
    ref_mapping_path = Path(project["prompts"]["reference_mapping_path"])
    save_json(subject_registry_path, {"project_id": project["project_id"], "subjects": profiles})
    save_json(
        entity_registry_path,
        {
            "project_id": project["project_id"],
            "entities": [
                {
                    "entity_id": profile["subject_id"],
                    "entity_type": "character",
                    "recurring": True,
                    "identity_lock": "required" if profile["reference_policy"] == "required" else "optional",
                    "reference_policy": profile["reference_policy"],
                    "reference_ids": profile["reference_asset_ids"],
                    "appearance": {
                        "narrative_role": profile["narrative_role"],
                        "visual_markers": profile["visual_markers"],
                    },
                    "must_remain_constant": profile["forbidden_variation"],
                }
                for profile in profiles
            ],
        },
    )
    save_json(ref_assets_path, {"project_id": project["project_id"], "reference_assets": assets})
    save_json(
        ref_mapping_path,
        {
            asset["reference_asset_id"]: asset["path"]
            for asset in assets
            if asset.get("reference_asset_id") and asset.get("path")
        },
    )
    project["planning"]["status"] = "subject_registry_built"
    project["current_stage"] = "allocate_frames"
    save_project(project_json, project)
    print(subject_registry_path)
    print(entity_registry_path)
    print(ref_assets_path)
    print(ref_mapping_path)


if __name__ == "__main__":
    main()
