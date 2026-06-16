import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json
from prompt_continuity import build_continuity_bundle, build_scene_prompt, clean_text, run_prompt_package_qa


REFERENCE_ROLES = {
    "operator_entry": ("lead_operator", "support_operator"),
    "necklace_access": ("boutique_attendant",),
    "assault_moment": ("boutique_attendant", "support_operator"),
    "assault_aftermath": ("boutique_attendant", "support_operator"),
    "security_system": ("security_guard",),
    "delayed_reaction": ("boutique_attendant",),
    "operator_exit": ("lead_operator", "support_operator"),
}


def routed_reference_ids(shot_role: str, active_entity_ids: list[str], subject_map: dict[str, dict]) -> list[str]:
    ref_ids: list[str] = []
    for subject_id in REFERENCE_ROLES.get(shot_role, ()):
        if subject_id not in active_entity_ids:
            continue
        subject = subject_map.get(subject_id, {})
        for ref_id in subject.get("reference_asset_ids", []) or []:
            if ref_id not in ref_ids:
                ref_ids.append(ref_id)
    return ref_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--start-shot", type=int, default=1)
    parser.add_argument("--end-shot", type=int, default=0)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    prompt_package = load_json(Path(project["prompts"]["prompt_package_path"]))
    scene_plan = load_json(Path(project["scene_plan"]["scene_plan_path"]))
    subject_registry = load_json(Path(project["prompts"]["subject_registry_path"])) if Path(project["prompts"]["subject_registry_path"]).exists() else {"subjects": []}
    subject_map = {item["subject_id"]: item for item in subject_registry.get("subjects", []) if item.get("subject_id")}
    scenes = list(scene_plan.get("scenes", []))
    if args.end_shot:
        scenes = [
            scene for scene in scenes
            if args.start_shot <= int(scene.get("shot_index") or 0) <= args.end_shot
        ]

    source_text = " ".join(clean_text(scene.get("voice_text", "")) for scene in scenes)
    bundle = build_continuity_bundle(project, scenes, source_text)
    authored = []
    qa_items = []
    for scene in scenes:
        authored_scene = build_scene_prompt(scene, bundle)
        descriptor = authored_scene["semantic_descriptor"]
        record = {
            "scene_id": scene["scene_id"],
            "frame_id": scene.get("frame_id", ""),
            "beat_id": scene.get("beat_id", ""),
            "visual_goal": authored_scene["visual_goal"],
            "visualized_claim": clean_text(scene.get("voice_text", "")),
            "must_show": [clean_text(scene.get("voice_text", ""))],
            "scene_meaning": bundle["scene_semantics_map"][scene["scene_id"]]["semantic_action"],
            "narrative_purpose": scene.get("narrative_purpose", ""),
            "viewer_emotion": descriptor["viewer_emotion"],
            "visual_function": descriptor["visual_function"],
            "visual_strategy": descriptor["visual_strategy"],
            "visual_idea": bundle["scene_semantics_map"][scene["scene_id"]]["semantic_action"],
            "main_subject": authored_scene["primary_subject"],
            "primary_subject": authored_scene["primary_subject"],
            "secondary_subjects": [],
            "what_is_in_frame": bundle["scene_semantics_map"][scene["scene_id"]]["semantic_action"],
            "environment": authored_scene["environment"],
            "camera": authored_scene["angle"],
            "composition": authored_scene["composition"],
            "lighting": authored_scene["lighting"],
            "mood": authored_scene["atmosphere"],
            "continuity_notes": authored_scene["continuity_focus"],
            "active_entity_ids": authored_scene["active_entity_ids"],
            "continuity_cast": authored_scene["continuity_cast"],
            "reference_ids": routed_reference_ids(authored_scene["shot_role"], authored_scene["active_entity_ids"], subject_map),
            "continuity_mode": "profiled",
            "voiceover_summary": clean_text(scene.get("voice_text", "")),
            "event_clarity_required": descriptor["event_clarity_required"],
            "event_type": descriptor["event_type"],
            "event_priority_reason": descriptor.get("fallback_reason", ""),
            "negative_prompt": "text, subtitle, logo, watermark, fake UI, unreadable signage, glamorized criminal hero shot, random replacement character, distorted hands, plastic skin",
            "beat_priority": authored_scene["beat_priority"],
            "key_beat": authored_scene["key_beat"],
            "variant_count": 2 if authored_scene["key_beat"] else 1,
            "shot_role": authored_scene["shot_role"],
            "shot_type": scene.get("shot_type") or authored_scene["angle"],
            "final_prompt": authored_scene["prompt"],
            "draft_prompt": authored_scene["prompt"],
        }
        qa_items.append(
            {
                **record,
                "prompt": record["final_prompt"],
                "scale": authored_scene["scale"],
                "angle": authored_scene["angle"],
                "lighting_family": authored_scene["lighting_family"],
                "density": authored_scene["density"],
                "semantic_descriptor": descriptor,
            }
        )
        authored.append(record)

    qa = run_prompt_package_qa(qa_items, bundle["theme_hint"])
    blocking_issues = [
        issue for issue in qa["issues"]
        if "adjacent-shot diversity too low" not in issue
        and "repeated subject/environment/role streak" not in issue
    ]
    qa_report_path = Path(project["prompts"]["llm_prompt_drafts_path"]).with_suffix(".qa.json")
    save_json(qa_report_path, qa)
    if blocking_issues:
        raise RuntimeError("Deterministic prompt QA failed:\n" + "\n".join(blocking_issues[:50]))

    drafts_path = Path(project["prompts"]["llm_prompt_drafts_path"])
    existing = load_json(drafts_path) if drafts_path.exists() else []
    authored_by_scene = {item["scene_id"]: item for item in authored}
    merged = []
    seen = set()
    for row in existing:
        scene_id = row.get("scene_id")
        if scene_id in authored_by_scene:
            merged.append(authored_by_scene[scene_id])
            seen.add(scene_id)
        else:
            merged.append(row)
    for row in authored:
        if row["scene_id"] not in seen:
            merged.append(row)
    save_json(drafts_path, merged)

    prompt_package["llm_prompt_drafts_path"] = str(drafts_path)
    save_json(Path(project["prompts"]["prompt_package_path"]), prompt_package)
    print(drafts_path)


if __name__ == "__main__":
    main()
