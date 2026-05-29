import argparse
from pathlib import Path

from pipeline_contracts import ReferenceBinding
from project_pipeline_utils import load_json, load_project, save_json, save_project


def candidate_subject_ids(frame: dict) -> list[str]:
    ordered: list[str] = []
    for value in frame.get("visible_subject_ids", []) or []:
        subject_id = str(value or "").strip()
        if subject_id and subject_id not in ordered:
            ordered.append(subject_id)
    primary_subject_id = str(frame.get("primary_subject_id") or "").strip()
    if primary_subject_id and primary_subject_id not in ordered:
        ordered.append(primary_subject_id)
    for entity in frame.get("entity_locks", []) or []:
        if not isinstance(entity, dict):
            continue
        policy = str(entity.get("reference_policy") or entity.get("identity_lock") or "").strip().lower()
        if policy not in {"required", "strict"}:
            continue
        subject_id = str(entity.get("entity_id") or "").strip()
        if subject_id and subject_id not in ordered:
            ordered.append(subject_id)
    return ordered


def resolve_reference_bindings(frame: dict, subject_map: dict, asset_map: dict) -> tuple[list[dict], list[str]]:
    flags: list[str] = []
    has_required_lock = any(
        isinstance(entity, dict)
        and str(entity.get("reference_policy") or entity.get("identity_lock") or "").strip().lower() in {"required", "strict"}
        for entity in frame.get("entity_locks", []) or []
    )
    if not frame.get("subject_visible") and not has_required_lock:
        return [], flags

    subject_ids = candidate_subject_ids(frame)
    if not subject_ids:
        flags.append("subject_visible_but_no_subject_id")
        return [], flags

    bindings: list[dict] = []
    for subject_id in subject_ids:
        subject = subject_map.get(subject_id)
        if not subject:
            flags.append(f"unknown_subject_id:{subject_id}")
            continue

        policy = str(subject.get("reference_policy", "optional")).strip().lower()
        asset_ids = list(subject.get("reference_asset_ids", []))
        if policy in {"required", "strict"} and not asset_ids:
            flags.append(f"missing_reference_for_required_subject:{subject_id}")
        if not asset_ids:
            continue

        valid_asset_ids: list[str] = []
        for asset_id in asset_ids[:3]:
            asset = asset_map.get(asset_id)
            if not asset or not Path(asset["path"]).exists():
                flags.append(f"reference_asset_file_missing:{subject_id}")
                continue
            valid_asset_ids.append(asset_id)

        if policy == "strict" and not valid_asset_ids:
            flags.append(f"strict_subject_without_reference:{subject_id}")
        if len(valid_asset_ids) > 3:
            flags.append(f"too_many_references_on_frame:{subject_id}")
        if not valid_asset_ids:
            continue

        binding = ReferenceBinding(
            subject_id=subject_id,
            reference_asset_ids=valid_asset_ids,
            usage="identity_and_wardrobe",
            strength="strict" if policy == "strict" else str(frame.get("subject_continuity_strength") or "medium"),
        )
        bindings.append(binding.__dict__)

    return bindings, sorted(set(flags))


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
