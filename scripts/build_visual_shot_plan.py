import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


ALLOWED_IMPORTANCE = {"hero", "supporting", "continuity", "bridge", "reuse"}
ALLOWED_GENERATION_MODES = {"unique", "derived", "reused"}


def clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def infer_importance(beat: dict, scene: dict, index: int, total: int) -> str:
    priority = clean_text(beat.get("visual_priority")).lower()
    if priority == "high" or index in {1, total}:
        return "hero"
    if priority == "medium":
        return "supporting"
    duration = float(scene.get("duration", 0) or 0)
    if duration <= 1.6:
        return "bridge"
    return "continuity"


def infer_generation_mode(importance: str, scene: dict, active_entities: list[str]) -> str:
    if scene.get("shot_role") in {"investigative_bridge", "documentary_bridge"}:
        return "derived"
    if importance == "bridge":
        return "derived"
    if len(active_entities) >= 2 and importance != "hero":
        return "reused"
    return "unique"


def infer_shot_type(scene: dict, beat: dict, importance: str) -> str:
    event_type = clean_text(scene.get("event_type") or beat.get("beat_role")).lower()
    if event_type in {"assault_moment", "theft_reveal", "access_moment"}:
        return "close evidence shot"
    if event_type in {"entry_moment"}:
        return "medium arrival shot"
    if importance == "hero":
        return "medium hero shot"
    if importance == "bridge":
        return "bridge shot"
    return "medium documentary shot"


def infer_visual_function(scene: dict, beat: dict, importance: str) -> str:
    for candidate in (
        scene.get("visual_function"),
        scene.get("narrative_purpose"),
        scene.get("shot_role"),
        beat.get("beat_role"),
    ):
        value = clean_text(candidate)
        if value:
            return value
    return "hook" if importance == "hero" else "explain"


def infer_film_block_id(scene: dict, beat: dict, index: int) -> str:
    for candidate in (
        scene.get("location_id"),
        scene.get("environment"),
        scene.get("global_scene_id"),
        beat.get("beat_role"),
    ):
        value = clean_text(candidate).lower().replace(" ", "_")
        if value:
            return f"film_block_{value}"
    return f"film_block_{index:04d}"


def infer_camera(scene: dict, beat: dict, visual_bible: dict, importance: str) -> str:
    if clean_text(scene.get("camera")):
        return clean_text(scene["camera"])
    camera_language = visual_bible.get("camera_language", {})
    lenses = camera_language.get("lenses", [])
    movements = camera_language.get("movement", [])
    if importance == "hero" and lenses:
        lens = lenses[0]
        movement = movements[0] if movements else "slow push-in"
        return f"{lens} {movement}".strip()
    if movements:
        return clean_text(movements[0])
    return clean_text(beat.get("beat_role")).replace("_", " ") or "documentary framing"


def infer_lighting(scene: dict, visual_bible: dict) -> str:
    if clean_text(scene.get("lighting")):
        return clean_text(scene["lighting"])
    color_script = visual_bible.get("color_script", {})
    if clean_text(color_script.get("base_palette")):
        return clean_text(color_script["base_palette"])
    return "motivated documentary lighting"


def build_default_plan(project: dict, scene_plan: dict, beats_payload: dict, continuity: dict, visual_bible: dict) -> dict:
    scenes = scene_plan.get("scenes", [])
    beats = beats_payload.get("beats", [])
    beats_by_scene = {beat.get("scene_id"): beat for beat in beats if beat.get("scene_id")}
    segment_entity_map = continuity.get("segment_entity_map", {})
    scene_entity_map = continuity.get("scene_entity_map", {})
    shots = []
    scene_groups = []
    scene_to_shot = {}
    total = len(scenes)

    for index, scene in enumerate(scenes, start=1):
        beat = beats_by_scene.get(scene["scene_id"], {})
        active_map = scene_entity_map.get(scene["scene_id"]) or segment_entity_map.get(str(scene.get("source_segment_id", "")), {})
        active_entities = list(dict.fromkeys(active_map.get("active_entities", []) or beat.get("entity_mentions", []) or scene.get("subject_ids", [])))
        importance = infer_importance(beat, scene, index, total)
        generation_mode = infer_generation_mode(importance, scene, active_entities)
        shot_id = clean_text(scene.get("shot_id")) or f"shot_{index:04d}"
        source_shot_id = shot_id
        must_show = [clean_text(item) for item in beat.get("must_visualize", []) if clean_text(item)]
        if not must_show:
            fallback = clean_text(scene.get("what_is_in_frame") or scene.get("visual_goal") or scene.get("voice_text"))
            if fallback:
                must_show = [fallback]
        film_block_id = infer_film_block_id(scene, beat, index)
        shot_record = {
            "shot_id": shot_id,
            "importance": importance,
            "generation_mode": generation_mode,
            "primary_scene_id": scene["scene_id"],
            "beat_ids": [clean_text(beat.get("beat_id")) or f"beat_{index:04d}"],
            "scene_ids": [scene["scene_id"]],
            "shot_type": infer_shot_type(scene, beat, importance),
            "visual_function": infer_visual_function(scene, beat, importance),
            "primary_entity_ids": active_entities,
            "must_show": must_show,
            "film_block_id": film_block_id,
            "visual_anchor": clean_text(scene.get("primary_subject") or scene.get("main_subject") or must_show[0] if must_show else scene.get("voice_text")),
            "off_topic_risk": "low" if must_show else "medium",
            "prompt_strategy": "ground every prompt in beat-level observable action and continuity-locked entities",
            "primary_subject": clean_text(scene.get("primary_subject") or scene.get("main_subject")),
            "camera": infer_camera(scene, beat, visual_bible, importance),
            "lighting": infer_lighting(scene, visual_bible),
            "transition_in": "cut",
            "transition_out": "cut_on_phrase_end",
        }
        shots.append(shot_record)
        scene_groups.append(
            {
                "group_id": f"group_{index:04d}",
                "importance": importance,
                "visual_strategy": shot_record["visual_function"],
                "shot_id": shot_id,
                "scenes": [scene["scene_id"]],
                "variation_notes": {scene["scene_id"]: ""},
            }
        )
        scene_to_shot[scene["scene_id"]] = {
            "shot_id": shot_id,
            "generation_mode": generation_mode,
            "source_shot_id": source_shot_id,
            "variation_note": "",
            "beat_id": shot_record["beat_ids"][0],
        }

    return {
        "project_id": project["project_id"],
        "quality_mode": project["prompts"].get("quality_mode", "standard"),
        "total_scenes": total,
        "target_unique_shots": sum(1 for shot in shots if shot["generation_mode"] == "unique"),
        "actual_unique_shots": sum(1 for shot in shots if shot["generation_mode"] == "unique"),
        "planning_source": "narration_beats.json",
        "scene_groups": scene_groups,
        "shots": shots,
        "scene_to_shot": scene_to_shot,
    }


def normalize_plan(raw_plan: dict, scene_ids: set[str], quality_mode: str) -> dict:
    scene_groups = raw_plan.get("scene_groups", [])
    shots = raw_plan.get("shots", [])
    scene_to_shot = raw_plan.get("scene_to_shot", {})

    shots_by_id = {}
    normalized_shots = []
    for shot in shots:
        shot_id = clean_text(shot.get("shot_id"))
        if not shot_id or shot_id in shots_by_id:
            continue
        importance = clean_text(shot.get("importance", "supporting")).lower() or "supporting"
        if importance not in ALLOWED_IMPORTANCE:
            importance = "supporting"
        generation_mode = clean_text(shot.get("generation_mode", "unique")).lower() or "unique"
        if generation_mode not in ALLOWED_GENERATION_MODES:
            generation_mode = "unique"
        scene_ids_for_shot = [scene_id for scene_id in shot.get("scene_ids", []) if scene_id in scene_ids]
        primary_scene_id = clean_text(shot.get("primary_scene_id")) or (scene_ids_for_shot[0] if scene_ids_for_shot else "")
        normalized = {
            "shot_id": shot_id,
            "importance": importance,
            "generation_mode": generation_mode,
            "primary_scene_id": primary_scene_id,
            "beat_ids": [clean_text(beat_id) for beat_id in shot.get("beat_ids", []) if clean_text(beat_id)],
            "scene_ids": scene_ids_for_shot,
            "shot_type": clean_text(shot.get("shot_type", "medium shot")) or "medium shot",
            "visual_function": clean_text(shot.get("visual_function", "explain")) or "explain",
            "primary_entity_ids": [clean_text(entity_id) for entity_id in shot.get("primary_entity_ids", []) if clean_text(entity_id)],
            "must_show": [clean_text(item) for item in shot.get("must_show", []) if clean_text(item)],
            "film_block_id": clean_text(shot.get("film_block_id", shot_id)) or shot_id,
            "visual_anchor": clean_text(shot.get("visual_anchor")),
            "off_topic_risk": clean_text(shot.get("off_topic_risk", "unknown")) or "unknown",
            "prompt_strategy": clean_text(shot.get("prompt_strategy")),
            "primary_subject": clean_text(shot.get("primary_subject")),
            "camera": clean_text(shot.get("camera")),
            "lighting": clean_text(shot.get("lighting")),
            "transition_in": clean_text(shot.get("transition_in", "cut")) or "cut",
            "transition_out": clean_text(shot.get("transition_out", "cut")) or "cut",
        }
        shots_by_id[shot_id] = normalized
        normalized_shots.append(normalized)

    normalized_scene_to_shot = {}
    for scene_id, mapping in scene_to_shot.items():
        if scene_id not in scene_ids:
            continue
        shot_id = clean_text(mapping.get("shot_id"))
        if shot_id not in shots_by_id:
            continue
        generation_mode = clean_text(mapping.get("generation_mode", shots_by_id[shot_id]["generation_mode"])).lower() or shots_by_id[shot_id]["generation_mode"]
        if generation_mode not in ALLOWED_GENERATION_MODES:
            generation_mode = shots_by_id[shot_id]["generation_mode"]
        normalized_scene_to_shot[scene_id] = {
            "shot_id": shot_id,
            "generation_mode": generation_mode,
            "source_shot_id": clean_text(mapping.get("source_shot_id", shot_id)) or shot_id,
            "variation_note": clean_text(mapping.get("variation_note")),
            "beat_id": clean_text(mapping.get("beat_id")),
        }

    for group in scene_groups:
        shot_id = clean_text(group.get("shot_id"))
        if shot_id not in shots_by_id:
            continue
        for scene_id in group.get("scenes", []):
            if scene_id not in scene_ids or scene_id in normalized_scene_to_shot:
                continue
            normalized_scene_to_shot[scene_id] = {
                "shot_id": shot_id,
                "generation_mode": shots_by_id[shot_id]["generation_mode"],
                "source_shot_id": shot_id,
                "variation_note": clean_text(group.get("variation_notes", {}).get(scene_id, "")),
                "beat_id": "",
            }

    return {
        "project_id": raw_plan.get("project_id"),
        "quality_mode": quality_mode,
        "total_scenes": len(scene_ids),
        "target_unique_shots": int(raw_plan.get("target_unique_shots", len(normalized_shots)) or len(normalized_shots)),
        "actual_unique_shots": len([shot for shot in normalized_shots if shot["generation_mode"] == "unique"]),
        "planning_source": clean_text(raw_plan.get("planning_source", "narration_beats.json")) or "narration_beats.json",
        "scene_groups": scene_groups,
        "shots": normalized_shots,
        "scene_to_shot": normalized_scene_to_shot,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--input-json", help="Optional authored visual_shot_plan.json to normalize into the project path.")
    parser.add_argument("--quality-mode", choices=["premium", "standard", "fast"])
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    narration_beats_path = Path(project["planning"]["narration_beats_path"])
    continuity_path = Path(project["planning"]["continuity_map_json_path"])
    visual_bible_path = Path(project["prompts"]["visual_bible_path"])
    output_path = Path(project["prompts"]["visual_shot_plan_path"])
    quality_mode = args.quality_mode or project["prompts"].get("quality_mode", "standard")

    scene_plan = load_json(scene_plan_path)
    beats_payload = load_json(narration_beats_path)
    continuity = load_json(continuity_path) if continuity_path.exists() else {}
    visual_bible = load_json(visual_bible_path) if visual_bible_path.exists() else {}
    scene_ids = {scene["scene_id"] for scene in scene_plan.get("scenes", []) if scene.get("scene_id")}
    if not scene_ids:
        raise RuntimeError("scene_plan has no scenes; cannot build visual_shot_plan")

    if args.input_json:
        raw_plan = load_json(Path(args.input_json).resolve())
        plan = normalize_plan(raw_plan, scene_ids, quality_mode)
    else:
        plan = build_default_plan(project, scene_plan, beats_payload, continuity, visual_bible)
        plan["quality_mode"] = quality_mode

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, plan)

    project["prompts"]["quality_mode"] = quality_mode
    project["prompts"]["visual_shot_plan_path"] = str(output_path)
    project["prompts"]["visual_shot_plan_status"] = "planned"
    project["current_stage"] = "build_frame_briefs"
    save_project(project_json, project)

    print(output_path)


if __name__ == "__main__":
    main()
