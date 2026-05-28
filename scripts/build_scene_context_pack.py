import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


DEFAULT_STYLE_SUMMARY = (
    "Ultra-realistic cinematic documentary still, natural light, rich organic textures, "
    "realistic anatomy when relevant, shallow depth of field when useful, 16:9 composition, no text."
)


def read_source_text(project: dict) -> str:
    candidates = [
        project.get("rewrite", {}).get("approved_script_path"),
        project.get("rewrite", {}).get("rewritten_script_path"),
        project.get("rewrite", {}).get("source_text_path"),
        project.get("inputs", {}).get("raw_text_path"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            text = path.read_text(encoding="utf-8-sig").strip()
            if text:
                return text
    return ""


def summarize_story(source_text: str, max_chars: int = 900) -> str:
    if not source_text:
        return ""
    clean = " ".join(source_text.split())
    return clean[:max_chars].strip()


def derive_master_subject(project: dict, source_text: str, style_guide: dict) -> str:
    if style_guide.get("main_subject_full"):
        return str(style_guide["main_subject_full"]).strip()
    meta_title = str(project.get("meta", {}).get("title", "")).strip()
    if meta_title:
        return meta_title
    if source_text:
        first_line = next((line.strip() for line in source_text.splitlines() if line.strip()), "")
        if first_line:
            return first_line[:160]
    return "main documentary subject from the narration"


def profile_map(entities: list[dict]) -> dict[str, dict]:
    return {str(entity.get("entity_id", "")).strip(): entity for entity in entities if str(entity.get("entity_id", "")).strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)

    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    style_guide_path = Path(
        project["prompts"].get("style_guide_path")
        or (Path(project["meta"]["project_root"]) / "prompts" / "style_guide.json")
    )
    continuity_path = Path(project["planning"]["continuity_map_json_path"])
    output_path = Path(
        project["prompts"].get("scene_context_pack_path")
        or (Path(project["meta"]["project_root"]) / "prompts" / "scene_context_pack.json")
    )

    scene_plan = load_json(scene_plan_path)
    package = load_json(prompt_package_path)
    style_guide = load_json(style_guide_path) if style_guide_path.exists() else {}
    continuity = load_json(continuity_path) if continuity_path.exists() else {}

    scenes = scene_plan.get("scenes", [])
    items = package.get("items", [])
    item_by_scene = {item["scene_id"]: item for item in items}
    source_text = read_source_text(project)

    story_arc_summary = summarize_story(source_text)
    source_language = project["meta"].get("language", "auto")
    prompt_language = project["prompts"].get("prompt_language", "English")
    style_summary = (
        style_guide.get("style_summary")
        or project["prompts"].get("global_style_summary")
        or DEFAULT_STYLE_SUMMARY
    )
    master_subject = derive_master_subject(project, source_text, style_guide)

    character_map = profile_map(continuity.get("character_profiles", []))
    object_map = profile_map(continuity.get("object_profiles", []))
    location_map = profile_map(continuity.get("location_profiles", []))
    scene_entity_map = continuity.get("scene_entity_map", {})
    segment_entity_map = continuity.get("segment_entity_map", {})
    continuity_expected = bool(project["workflow"].get("is_sequence", True))
    continuity_fallback_used = continuity_expected and not continuity_path.exists()

    context_pack = []
    for index, scene in enumerate(scenes):
        prev_text = scenes[index - 1]["voice_text"] if index > 0 else ""
        next_text = scenes[index + 1]["voice_text"] if index + 1 < len(scenes) else ""
        prev_item = item_by_scene.get(scenes[index - 1]["scene_id"], {}) if index > 0 else {}
        next_item = item_by_scene.get(scenes[index + 1]["scene_id"], {}) if index + 1 < len(scenes) else {}
        item = item_by_scene.get(scene["scene_id"], {})
        scene_continuity = scene_entity_map.get(scene["scene_id"], {})
        if not scene_continuity:
            scene_continuity = segment_entity_map.get(str(scene.get("source_segment_id", "")), {})
        active_entity_ids = list(dict.fromkeys(scene_continuity.get("active_entities", [])))

        context_pack.append(
            {
                "project_id": project["project_id"],
                "scene_id": scene["scene_id"],
                "shot_index": scene["shot_index"],
                "start": scene["start"],
                "end": scene["end"],
                "duration": scene["duration"],
                "voice_text": scene.get("voice_text", ""),
                "context_before": prev_text,
                "context_after": next_text,
                "source_language": source_language,
                "prompt_language": prompt_language,
                "scene_archetype_hint": item.get("scene_archetype") or scene.get("scene_archetype"),
                "project_theme": style_guide.get("theme"),
                "style_summary": style_summary,
                "master_subject": master_subject,
                "story_arc_summary": story_arc_summary,
                "previous_role_hint": prev_item.get("shot_role"),
                "next_role_hint": next_item.get("shot_role"),
                "reference_ids": item.get("reference_ids", scene.get("reference_ids", [])),
                "reference_bindings": item.get("reference_bindings", scene.get("reference_bindings", [])),
                "mentioned_subject_ids": item.get("mentioned_subject_ids", scene.get("mentioned_subject_ids", [])),
                "visible_subject_ids": item.get("visible_subject_ids", scene.get("visible_subject_ids", [])),
                "subject_visible": bool(item.get("subject_visible", scene.get("subject_visible", False))),
                "primary_subject_id": item.get("primary_subject_id", scene.get("primary_subject_id")),
                "event_clarity_required": bool(item.get("event_clarity_required", scene.get("event_clarity_required", False))),
                "event_type": item.get("event_type") or scene.get("event_type"),
                "event_priority_reason": item.get("event_priority_reason") or scene.get("event_priority_reason"),
                "continuity_world": continuity.get("continuity_world"),
                "continuity_rules": continuity.get("continuity_rules", []),
                "recurring_motifs": continuity.get("recurring_motifs", []),
                "theme_hint": continuity.get("theme_hint"),
                "continuity_mode": "profiled" if continuity_path.exists() else "fallback",
                "continuity_expected": continuity_expected,
                "continuity_fallback_used": continuity_fallback_used,
                "active_entity_ids": active_entity_ids,
                "active_character_profiles": [character_map[entity_id] for entity_id in active_entity_ids if entity_id in character_map],
                "active_object_profiles": [object_map[entity_id] for entity_id in active_entity_ids if entity_id in object_map],
                "active_location_profiles": [location_map[entity_id] for entity_id in active_entity_ids if entity_id in location_map],
                "continuity_focus": scene_continuity.get("continuity_focus", ""),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, context_pack)
    project["prompts"]["scene_context_pack_path"] = str(output_path)
    project["prompts"]["status"] = "context_ready"
    save_project(project_json, project)
    print(output_path)


if __name__ == "__main__":
    main()
