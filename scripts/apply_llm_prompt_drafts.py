import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project
from prompt_safety import lint_prompt_observability


REQUIRED_FIELDS = ["scene_id", "visual_goal", "final_prompt"]


def validate_record(record: dict) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not str(record.get(field, "")).strip():
            errors.append(f"Missing required field `{field}`")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--drafts-json")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)

    drafts_path = Path(
        args.drafts_json
        or project["prompts"].get("llm_prompt_drafts_path")
        or (Path(project["meta"]["project_root"]) / "prompts" / "llm_prompt_drafts.json")
    ).resolve()
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    prompt_review_path = Path(project["prompts"]["prompt_review_path"])

    if not drafts_path.exists():
        raise FileNotFoundError(f"LLM prompt drafts file not found: {drafts_path}")

    drafts_payload = load_json(drafts_path)
    if not isinstance(drafts_payload, list):
        raise RuntimeError("LLM prompt drafts must be a JSON array")

    prompt_package = load_json(prompt_package_path)
    scene_plan = load_json(scene_plan_path)

    drafts_by_scene = {}
    validation_errors: list[str] = []
    for record in drafts_payload:
        scene_id = str(record.get("scene_id", "")).strip()
        if not scene_id:
            validation_errors.append("Draft record missing scene_id")
            continue
        record_errors = validate_record(record)
        if record_errors:
            validation_errors.extend(f"{scene_id}: {msg}" for msg in record_errors)
            continue
        drafts_by_scene[scene_id] = record

    if validation_errors:
        raise RuntimeError("Invalid LLM prompt drafts:\n" + "\n".join(validation_errors))

    package_items = prompt_package.get("items", [])
    scene_records = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", [])}
    missing_scene_ids = []

    for item in package_items:
        scene_id = item["scene_id"]
        draft = drafts_by_scene.get(scene_id)
        if not draft:
            missing_scene_ids.append(scene_id)
            continue

        item["scene_meaning"] = draft.get("scene_meaning", item.get("scene_meaning", ""))
        item["narrative_purpose"] = draft.get("narrative_purpose", item.get("narrative_purpose", ""))
        item["viewer_emotion"] = draft.get("viewer_emotion", item.get("viewer_emotion", ""))
        item["visual_function"] = draft.get("visual_function", item.get("visual_function", ""))
        item["visual_strategy"] = draft.get("visual_strategy", item.get("visual_strategy", ""))
        item["visual_idea"] = draft.get("visual_idea", item.get("visual_idea", ""))
        item["main_subject"] = draft.get("main_subject", item.get("main_subject", ""))
        item["environment"] = draft.get("environment", item.get("environment", ""))
        item["visual_goal"] = draft["visual_goal"]
        item["draft_prompt"] = draft.get("draft_prompt", draft["final_prompt"])
        item["final_prompt"] = draft["final_prompt"]
        item["prompt"] = draft["final_prompt"]
        item["status"] = "drafted"
        item["scene_importance"] = draft.get("scene_importance")
        item["shot_id"] = draft.get("shot_id")
        item["source_shot_id"] = draft.get("source_shot_id")
        item["generation_mode"] = draft.get("generation_mode")
        item["variation_note"] = draft.get("variation_note")
        item["shot_role"] = draft.get("shot_role")
        item["primary_subject"] = draft.get("primary_subject")
        item["secondary_subjects"] = draft.get("secondary_subjects", [])
        item["what_is_in_frame"] = draft.get("what_is_in_frame")
        item["camera"] = draft.get("camera")
        item["composition"] = draft.get("composition")
        item["lighting"] = draft.get("lighting")
        item["mood"] = draft.get("mood")
        item["continuity_notes"] = draft.get("continuity_notes")
        item["active_entity_ids"] = draft.get("active_entity_ids", [])
        item["continuity_cast"] = draft.get("continuity_cast", [])
        item["voiceover_summary"] = draft.get("voiceover_summary", "")
        item["reference_ids"] = draft.get("reference_ids", item.get("reference_ids", []))
        item["continuity_mode"] = draft.get("continuity_mode", item.get("continuity_mode"))
        item["event_clarity_required"] = draft.get("event_clarity_required", item.get("event_clarity_required", False))
        item["event_type"] = draft.get("event_type", item.get("event_type", ""))
        item["event_priority_reason"] = draft.get("event_priority_reason", item.get("event_priority_reason", ""))
        item["negative_prompt"] = draft.get("negative_prompt")
        item["notes"] = ["Prompt authored by LLM and ingested by Python"]

        scene = scene_records.get(scene_id)
        if scene:
            original_timing = (scene["scene_id"], scene["start"], scene["end"], scene["duration"])
            scene["scene_meaning"] = item["scene_meaning"]
            scene["narrative_purpose"] = item["narrative_purpose"]
            scene["viewer_emotion"] = item["viewer_emotion"]
            scene["visual_function"] = item["visual_function"]
            scene["visual_strategy"] = item["visual_strategy"]
            scene["visual_idea"] = item["visual_idea"]
            scene["main_subject"] = item["main_subject"]
            scene["environment"] = item["environment"]
            scene["visual_goal"] = draft["visual_goal"]
            scene["draft_prompt"] = item["draft_prompt"]
            scene["final_prompt"] = draft["final_prompt"]
            scene["prompt"] = draft["final_prompt"]
            scene["scene_importance"] = draft.get("scene_importance")
            scene["shot_id"] = draft.get("shot_id")
            scene["source_shot_id"] = draft.get("source_shot_id")
            scene["generation_mode"] = draft.get("generation_mode")
            scene["variation_note"] = draft.get("variation_note")
            scene["shot_role"] = draft.get("shot_role")
            scene["primary_subject"] = draft.get("primary_subject")
            scene["secondary_subjects"] = draft.get("secondary_subjects", [])
            scene["what_is_in_frame"] = draft.get("what_is_in_frame")
            scene["camera"] = draft.get("camera")
            scene["composition"] = draft.get("composition")
            scene["lighting"] = draft.get("lighting")
            scene["mood"] = draft.get("mood")
            scene["continuity_notes"] = draft.get("continuity_notes")
            scene["active_entity_ids"] = draft.get("active_entity_ids", [])
            scene["continuity_cast"] = draft.get("continuity_cast", [])
            scene["voiceover_summary"] = draft.get("voiceover_summary", "")
            scene["reference_ids"] = draft.get("reference_ids", scene.get("reference_ids", []))
            scene["continuity_mode"] = draft.get("continuity_mode", scene.get("continuity_mode"))
            scene["event_clarity_required"] = draft.get("event_clarity_required", scene.get("event_clarity_required", False))
            scene["event_type"] = draft.get("event_type", scene.get("event_type", ""))
            scene["event_priority_reason"] = draft.get("event_priority_reason", scene.get("event_priority_reason", ""))
            scene["negative_prompt"] = draft.get("negative_prompt")
            scene["notes"] = ["Prompt authored by LLM and ingested by Python"]
            scene.setdefault("qa_status", {})
            scene["qa_status"]["prompt_qa"] = "pending"
            if original_timing != (scene["scene_id"], scene["start"], scene["end"], scene["duration"]):
                raise RuntimeError(f"Timing mutated while applying prompt drafts for {scene_id}")

    if missing_scene_ids:
        raise RuntimeError(f"Missing LLM prompt drafts for {len(missing_scene_ids)} scenes")

    scene_plan["prompt_qa_status"] = "pending"
    prompt_package["llm_authored"] = True
    prompt_package["llm_prompt_drafts_path"] = str(drafts_path)
    save_json(prompt_package_path, prompt_package)
    save_json(scene_plan_path, scene_plan)
    save_json(final_scene_plan_path, scene_plan)

    review_lines = []
    for item in package_items:
        safety_warnings = lint_prompt_observability(
            prompt=str(item.get("final_prompt", "") or item.get("prompt", "")),
            primary_subject=str(item.get("primary_subject", "")),
            what_is_in_frame=str(item.get("what_is_in_frame", "")),
        )
        review_lines.extend(
            [
                f"Scene {item['shot_index']} ({item['scene_id']})",
                f"Voice text: {item.get('voice_text', '')}",
                f"Visual goal: {item.get('visual_goal', '')}",
                f"Primary subject: {item.get('primary_subject', '')}",
                f"Camera: {item.get('camera', '')}",
                f"Composition: {item.get('composition', '')}",
                f"Lighting: {item.get('lighting', '')}",
                f"Mood: {item.get('mood', '')}",
                f"Final prompt: {item.get('final_prompt', '')}",
                f"Prompt safety warnings: {' | '.join(safety_warnings) if safety_warnings else 'none'}",
                "",
            ]
        )
    prompt_review_path.write_text("\n".join(review_lines), encoding="utf-8")

    project["prompts"]["status"] = "draft"
    project["prompts"]["llm_prompt_drafts_path"] = str(drafts_path)
    project["current_stage"] = "generation_lock"
    save_project(project_json, project)

    print(prompt_package_path)
    print(scene_plan_path)
    print(final_scene_plan_path)
    print(prompt_review_path)


if __name__ == "__main__":
    main()
