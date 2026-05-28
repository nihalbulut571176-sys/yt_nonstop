import argparse
from pathlib import Path

from pipeline_contracts import ReferenceBinding
from project_pipeline_utils import load_json, load_project, save_json, save_project


def resolve_reference_bindings(frame: dict, subject_map: dict, asset_map: dict) -> tuple[list[dict], list[str]]:
    flags: list[str] = []
    if not frame.get("subject_visible"):
        return [], flags

    primary_subject_id = frame.get("primary_subject_id")
    if not primary_subject_id:
        flags.append("subject_visible_but_no_subject_id")
        return [], flags

    subject = subject_map.get(primary_subject_id)
    if not subject:
        flags.append("unknown_subject_id")
        return [], flags

    policy = str(subject.get("reference_policy", "optional"))
    asset_ids = list(subject.get("reference_asset_ids", []))
    if policy in {"required", "strict"} and not asset_ids:
        flags.append("missing_reference_for_required_subject")
    if not asset_ids:
        return [], flags

    valid_asset_ids = []
    for asset_id in asset_ids[:3]:
        asset = asset_map.get(asset_id)
        if not asset:
            flags.append("reference_asset_file_missing")
            continue
        if not Path(asset["path"]).exists():
            flags.append("reference_asset_file_missing")
            continue
        valid_asset_ids.append(asset_id)

    if policy == "strict" and not valid_asset_ids:
        flags.append("strict_subject_without_reference")
    if len(valid_asset_ids) > 3:
        flags.append("too_many_references_on_frame")

    if not valid_asset_ids:
        return [], flags

    binding = ReferenceBinding(
        subject_id=primary_subject_id,
        reference_asset_ids=valid_asset_ids,
        usage="identity_and_wardrobe",
        strength="strict" if policy == "strict" else str(frame.get("subject_continuity_strength") or "medium"),
    )
    return [binding.__dict__], flags


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    frame_briefs_path = Path(project["planning"]["frame_briefs_json_path"])
    subject_registry_path = Path(project["prompts"]["subject_registry_path"])
    assets_path = Path(project["prompts"]["reference_assets_manifest_path"])
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])

    frame_briefs = load_json(frame_briefs_path)
    subject_payload = load_json(subject_registry_path) if subject_registry_path.exists() else {"subjects": []}
    assets_payload = load_json(assets_path) if assets_path.exists() else {"reference_assets": []}
    scene_plan = load_json(scene_plan_path)

    subject_map = {item["subject_id"]: item for item in subject_payload.get("subjects", [])}
    asset_map = {item["reference_asset_id"]: item for item in assets_payload.get("reference_assets", [])}
    scene_by_id = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", [])}
    report_rows = []

    for frame in frame_briefs:
        bindings, flags = resolve_reference_bindings(frame, subject_map, asset_map)
        if bindings and not frame.get("subject_visible"):
            flags.append("reference_attached_without_visible_subject")
        frame["reference_bindings"] = bindings
        frame["reference_ids"] = [asset_id for binding in bindings for asset_id in binding["reference_asset_ids"]]
        frame["reference_images"] = [asset_map[asset_id]["path"] for asset_id in frame["reference_ids"] if asset_id in asset_map]
        frame["reference_strength"] = bindings[0]["strength"] if bindings else "none"
        frame["reference_usage"] = bindings[0]["usage"] if bindings else "none"
        frame["reference_binding_flags"] = sorted(set(flags))

        scene = scene_by_id.get(frame["scene_id"])
        if scene is not None:
            scene["reference_bindings"] = bindings
            scene["reference_ids"] = list(frame["reference_ids"])
            scene["reference_images"] = list(frame["reference_images"])
            scene["reference_strength"] = frame["reference_strength"]
            scene["reference_usage"] = frame["reference_usage"]
            scene["mentioned_subject_ids"] = list(frame.get("mentioned_subject_ids", []))
            scene["visible_subject_ids"] = list(frame.get("visible_subject_ids", []))
            scene["subject_visible"] = bool(frame.get("subject_visible"))

        report_rows.append(
            {
                "frame_id": frame["frame_id"],
                "scene_id": frame["scene_id"],
                "primary_subject_id": frame.get("primary_subject_id"),
                "subject_visible": frame.get("subject_visible"),
                "reference_count": len(frame["reference_ids"]),
                "flags": frame["reference_binding_flags"],
            }
        )

    save_json(frame_briefs_path, frame_briefs)
    save_json(scene_plan_path, scene_plan)
    save_json(Path(project["planning"]["reference_binding_report_path"]), report_rows)
    project["planning"]["status"] = "reference_assets_attached"
    project["current_stage"] = "generate_fastgen_prompt_drafts"
    save_project(project_json, project)
    print(frame_briefs_path)


if __name__ == "__main__":
    main()
