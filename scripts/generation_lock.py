import argparse
from pathlib import Path

from pipeline_contracts import (
    GenerationLockedFrame,
    build_reference_prefix,
    derive_continuity_note,
    derive_generation_block,
    derive_motion_prompt,
    is_generic_prompt,
    normalize_text,
    prompt_has_text_conflict,
    prompt_mentions_brand,
    prompt_restates_srt,
    stable_hash,
    write_csv,
)
from project_pipeline_utils import load_json, load_project, save_json, save_project


def lock_record(frame_brief: dict, scene: dict, previous_prompt: str) -> tuple[dict, list[str], list[str]]:
    image_prompt = str(scene.get("final_prompt") or scene.get("prompt") or "").strip()
    negative_prompt = str(scene.get("negative_prompt") or "").strip()
    continuity_note = str(scene.get("continuity_notes") or derive_continuity_note(frame_brief)).strip()
    motion_prompt = str(scene.get("motion_prompt") or derive_motion_prompt(frame_brief)).strip()
    reference_bindings = list(scene.get("reference_bindings") or frame_brief.get("reference_bindings") or [])
    reference_ids = list(scene.get("reference_ids", []))
    if not reference_ids:
        reference_ids = [asset_id for binding in reference_bindings for asset_id in binding.get("reference_asset_ids", [])]
    reference_images = list(scene.get("reference_images", []))
    continuity_mode = str(scene.get("continuity_mode") or "").strip().lower()

    errors: list[str] = []
    warnings: list[str] = []
    if not image_prompt:
        errors.append("missing_image_prompt")
    if not negative_prompt:
        errors.append("missing_negative")
    if not motion_prompt:
        errors.append("missing_motion")
    if not continuity_note and not frame_brief.get("continuity_tags"):
        errors.append("missing_continuity")
    if continuity_mode == "fallback":
        warnings.append("continuity_fallback")
    if image_prompt and prompt_restates_srt(image_prompt, frame_brief.get("srt_text", "")):
        errors.append("direct_srt_in_prompt")
    if image_prompt and prompt_has_text_conflict(image_prompt):
        errors.append("text_conflict")
    if image_prompt and prompt_mentions_brand(image_prompt):
        warnings.append("brand_risk")
    if image_prompt and is_generic_prompt(image_prompt):
        warnings.append("too_generic")
    if previous_prompt and normalize_text(previous_prompt).lower() == normalize_text(image_prompt).lower():
        warnings.append("neighbor_duplicate")

    status = "locked"
    if errors:
        status = "failed"
    elif warnings:
        status = "locked_with_warnings"

    locked = GenerationLockedFrame(
        frame_id=frame_brief["frame_id"],
        beat_id=frame_brief["beat_id"],
        image_prompt=image_prompt,
        negative_prompt=negative_prompt,
        motion_prompt=motion_prompt,
        continuity_note=continuity_note,
        generation_lock_status=status,
        qc_risk="; ".join(warnings + errors) if warnings or errors else "low",
        validation_flags=warnings + errors,
        reference_ids=reference_ids,
        frame_brief_hash=frame_brief["frame_brief_hash"],
        prompt_contract_version=frame_brief["prompt_contract_version"],
        llm_model_id=frame_brief["llm_model_id"],
        llm_prompt_template_version=frame_brief["llm_prompt_template_version"],
        generation_lock_version=frame_brief["generation_lock_version"],
    )
    payload = locked.__dict__
    payload["reference_bindings"] = reference_bindings
    payload["reference_images"] = reference_images
    payload["visualized_claim"] = str(scene.get("visualized_claim") or frame_brief.get("visualized_claim") or "")
    payload["must_show"] = list(scene.get("must_show") or frame_brief.get("must_show") or [])
    payload["reference_strength"] = scene.get("reference_strength") or frame_brief.get("subject_continuity_strength") or "none"
    payload["reference_usage"] = scene.get("reference_usage") or (reference_bindings[0]["usage"] if reference_bindings else "none")
    payload["reference_prefix"] = build_reference_prefix(reference_ids)
    payload["generator_block"] = derive_generation_block(payload["reference_prefix"], image_prompt, negative_prompt)
    payload["locked_hash"] = stable_hash(payload)
    return payload, errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    frame_briefs = load_json(Path(project["planning"]["frame_briefs_json_path"]))
    scene_source = Path(project["prompts"]["final_scene_plan_path"])
    if not scene_source.exists():
        scene_source = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = load_json(scene_source)
    scenes_by_frame = {scene.get("frame_id"): scene for scene in scene_plan.get("scenes", [])}

    locked_rows = []
    report_lines = ["# Generation Lock Report", ""]
    previous_prompt = ""
    for frame_brief in frame_briefs:
        scene = scenes_by_frame.get(frame_brief["frame_id"])
        if scene is None:
            raise RuntimeError(f"Missing scene for frame_id {frame_brief['frame_id']}")
        locked, errors, warnings = lock_record(frame_brief, scene, previous_prompt)
        previous_prompt = locked["image_prompt"]
        locked_rows.append(locked)
        report_lines.extend(
            [
                f"## {locked['frame_id']}",
                f"Status: {locked['generation_lock_status']}",
                f"Flags: {', '.join(locked['validation_flags']) if locked['validation_flags'] else 'none'}",
                "",
            ]
        )

    json_path = Path(project["prompts"]["generation_locked_json_path"])
    csv_path = Path(project["prompts"]["generation_locked_csv_path"])
    report_path = Path(project["logs"]["generation_lock_report_path"])
    save_json(json_path, locked_rows)
    write_csv(csv_path, locked_rows)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    statuses = {row["generation_lock_status"] for row in locked_rows}
    if "failed" in statuses:
        project["prompts"]["status"] = "needs_rewrite"
    else:
        project["prompts"]["status"] = "locked"
    project["current_stage"] = "quality_assurance"
    save_project(project_json, project)
    print(json_path)


if __name__ == "__main__":
    main()
