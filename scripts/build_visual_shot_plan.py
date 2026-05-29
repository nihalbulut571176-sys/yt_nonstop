import argparse
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project


ALLOWED_IMPORTANCE = {"hero", "supporting", "continuity", "bridge", "reuse"}
ALLOWED_GENERATION_DECISIONS = {
    "new_image",
    "new_angle_same_setup",
    "detail_insert",
    "reaction_shot",
    "establishing_shot",
    "hold_previous",
    "continuation_motion",
    "manual_asset",
}
NON_GENERATIVE_DECISIONS = {"hold_previous", "continuation_motion"}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def importance_from_slot(slot: dict[str, Any], index: int, total: int) -> str:
    priority = clean_text(slot.get("priority")).lower()
    if priority == "high" or index in {1, total}:
        return "hero"
    if priority == "medium":
        return "supporting"
    if slot.get("generation_decision") in NON_GENERATIVE_DECISIONS:
        return "reuse"
    return "continuity"


def infer_slot_shot_type(slot: dict[str, Any]) -> str:
    explicit = clean_text(slot.get("shot_type") or slot.get("shot_design"))
    if explicit:
        return explicit
    slot_type = clean_text(slot.get("slot_type")).lower()
    mapping = {
        "establishing_shot": "wide establishing shot",
        "character_action": "medium character action shot",
        "detail_insert": "close detail insert",
        "evidence_insert": "close evidence insert",
        "reaction_shot": "reaction shot",
        "context_detail": "context detail shot",
        "continuation_motion": "continuation motion hold",
    }
    return mapping.get(slot_type, "medium documentary shot")


def build_from_visual_allocation(project: dict[str, Any], allocation: dict[str, Any], continuity: dict[str, Any], visual_bible: dict[str, Any]) -> dict[str, Any]:
    visual_slots = allocation.get("visual_slots", [])
    if not visual_slots:
        raise RuntimeError("visual_allocation_plan has no visual_slots")
    scene_entity_map = continuity.get("scene_entity_map", {})
    segment_entity_map = continuity.get("segment_entity_map", {})
    shots: list[dict[str, Any]] = []
    scene_groups: list[dict[str, Any]] = []
    scene_to_shot: dict[str, dict[str, Any]] = {}
    visual_slot_to_shot: dict[str, dict[str, Any]] = {}
    total = len(visual_slots)
    for index, slot in enumerate(visual_slots, start=1):
        slot_id = clean_text(slot.get("visual_slot_id") or f"VS{index:04d}")
        decision = clean_text(slot.get("generation_decision") or "new_image").lower()
        if decision not in ALLOWED_GENERATION_DECISIONS:
            decision = "new_image"
        shot_id = clean_text(slot.get("shot_id") or f"shot_{index:04d}")
        scene_ids = [clean_text(item) for item in slot.get("scene_ids", []) if clean_text(item)]
        source_scene_id = clean_text(slot.get("source_scene_id") or (scene_ids[0] if scene_ids else ""))
        active_entities: list[str] = []
        for scene_id in scene_ids or [source_scene_id]:
            active_map = scene_entity_map.get(scene_id) or segment_entity_map.get(scene_id) or {}
            active_entities.extend(active_map.get("active_entities", []) or [])
        active_entities.extend(slot.get("primary_entity_ids", []) or [])
        active_entities = list(dict.fromkeys(clean_text(item) for item in active_entities if clean_text(item)))
        importance = importance_from_slot(slot, index, total)
        camera = clean_text(slot.get("camera"))
        if not camera:
            camera_language = visual_bible.get("camera_language", {}) if isinstance(visual_bible, dict) else {}
            movement = (camera_language.get("movement") or ["documentary framing"])[0]
            camera = clean_text(movement) or "documentary framing"
        lighting = clean_text(slot.get("lighting"))
        if not lighting:
            color_script = visual_bible.get("color_script", {}) if isinstance(visual_bible, dict) else {}
            lighting = clean_text(color_script.get("base_palette")) or "motivated documentary lighting"
        shot_record = {
            "shot_id": shot_id,
            "visual_slot_id": slot_id,
            "importance": importance,
            "generation_mode": decision,
            "generation_decision": decision,
            "primary_scene_id": source_scene_id,
            "source_scene_id": source_scene_id,
            "beat_ids": [clean_text(item) for item in slot.get("beat_ids", []) if clean_text(item)],
            "scene_ids": scene_ids or ([source_scene_id] if source_scene_id else []),
            "shot_type": infer_slot_shot_type(slot),
            "slot_type": clean_text(slot.get("slot_type") or "explanation_visual"),
            "visual_function": clean_text(slot.get("visual_function") or "show_spoken_idea"),
            "primary_entity_ids": active_entities,
            "must_show": [clean_text(item) for item in slot.get("must_show", []) if clean_text(item)],
            "film_block_id": clean_text(slot.get("film_block_id") or f"film_block_{index:04d}"),
            "visual_anchor": clean_text(slot.get("must_show", [""])[0] if slot.get("must_show") else slot.get("visualized_claim")),
            "visualized_claim": clean_text(slot.get("visualized_claim")),
            "off_topic_risk": "low" if slot.get("must_show") else "medium",
            "prompt_strategy": "ground the prompt in this authored visual slot, not in a generic scene summary",
            "primary_subject": clean_text(slot.get("primary_subject")),
            "camera": camera,
            "lighting": lighting,
            "transition_in": clean_text(slot.get("transition_in") or "cut"),
            "transition_out": clean_text(slot.get("transition_out") or "cut_on_phrase_end"),
            "variant_count": int(slot.get("variant_count", 0) or 0),
            "reason": clean_text(slot.get("reason")),
            "source_visual_slot_id": clean_text(slot.get("source_visual_slot_id")),
        }
        shots.append(shot_record)
        scene_groups.append(
            {
                "group_id": f"group_{index:04d}",
                "importance": importance,
                "visual_strategy": shot_record["visual_function"],
                "shot_id": shot_id,
                "visual_slot_id": slot_id,
                "scenes": shot_record["scene_ids"],
                "variation_notes": {scene_id: slot.get("reason", "") for scene_id in shot_record["scene_ids"]},
            }
        )
        mapping = {
            "shot_id": shot_id,
            "visual_slot_id": slot_id,
            "generation_mode": decision,
            "generation_decision": decision,
            "source_shot_id": clean_text(slot.get("source_visual_slot_id") or shot_id),
            "variation_note": clean_text(slot.get("reason")),
            "beat_id": shot_record["beat_ids"][0] if shot_record["beat_ids"] else "",
        }
        visual_slot_to_shot[slot_id] = mapping
        if source_scene_id and source_scene_id not in scene_to_shot:
            scene_to_shot[source_scene_id] = mapping
    generative_count = sum(1 for shot in shots if shot["generation_decision"] not in NON_GENERATIVE_DECISIONS)
    return {
        "project_id": project["project_id"],
        "quality_mode": project["prompts"].get("quality_mode", "standard"),
        "total_scenes": len({sid for shot in shots for sid in shot.get("scene_ids", [])}),
        "total_visual_slots": len(visual_slots),
        "target_unique_shots": generative_count,
        "actual_unique_shots": generative_count,
        "planning_source": "visual_allocation_plan.json",
        "scene_groups": scene_groups,
        "shots": shots,
        "scene_to_shot": scene_to_shot,
        "visual_slot_to_shot": visual_slot_to_shot,
    }


# Legacy fallback kept for non-sequence or old fixtures.
def build_default_plan(project: dict[str, Any], scene_plan: dict[str, Any], beats_payload: dict[str, Any], continuity: dict[str, Any], visual_bible: dict[str, Any]) -> dict[str, Any]:
    scenes = scene_plan.get("scenes", [])
    beats = beats_payload.get("beats", [])
    beats_by_scene = {beat.get("scene_id"): beat for beat in beats if beat.get("scene_id")}
    shots = []
    scene_groups = []
    scene_to_shot = {}
    for index, scene in enumerate(scenes, start=1):
        beat = beats_by_scene.get(scene.get("scene_id"), {})
        shot_id = clean_text(scene.get("shot_id")) or f"shot_{index:04d}"
        must_show = [clean_text(item) for item in beat.get("must_visualize", []) if clean_text(item)] or [clean_text(scene.get("voice_text"))]
        priority = clean_text(beat.get("visual_priority") or "low").lower()
        importance = "hero" if priority == "high" or index == 1 else "supporting" if priority == "medium" else "continuity"
        generation_mode = "new_image"
        record = {
            "shot_id": shot_id,
            "importance": importance,
            "generation_mode": generation_mode,
            "generation_decision": generation_mode,
            "primary_scene_id": scene.get("scene_id"),
            "source_scene_id": scene.get("scene_id"),
            "beat_ids": [clean_text(beat.get("beat_id")) or f"beat_{index:04d}"],
            "scene_ids": [scene.get("scene_id")],
            "shot_type": "medium documentary shot",
            "slot_type": "explanation_visual",
            "visual_function": clean_text(beat.get("beat_role") or scene.get("visual_function") or "explain"),
            "primary_entity_ids": list(dict.fromkeys(beat.get("entity_mentions", []) or scene.get("subject_ids", []) or [])),
            "must_show": must_show,
            "film_block_id": clean_text(scene.get("film_block_id") or scene.get("global_scene_id") or f"film_block_{index:04d}"),
            "visual_anchor": must_show[0],
            "visualized_claim": clean_text(beat.get("spoken_claim") or scene.get("visualized_claim") or scene.get("voice_text")),
            "off_topic_risk": "low",
            "prompt_strategy": "ground every prompt in beat-level observable action and continuity-locked entities",
            "primary_subject": clean_text(scene.get("primary_subject") or scene.get("main_subject")),
            "camera": clean_text(scene.get("camera") or "documentary framing"),
            "lighting": clean_text(scene.get("lighting") or "motivated documentary lighting"),
            "transition_in": "cut",
            "transition_out": "cut_on_phrase_end",
            "variant_count": 1,
        }
        shots.append(record)
        scene_groups.append({"group_id": f"group_{index:04d}", "importance": importance, "visual_strategy": record["visual_function"], "shot_id": shot_id, "scenes": [scene.get("scene_id")], "variation_notes": {scene.get("scene_id"): ""}})
        scene_to_shot[scene.get("scene_id")] = {"shot_id": shot_id, "generation_mode": generation_mode, "generation_decision": generation_mode, "source_shot_id": shot_id, "variation_note": "", "beat_id": record["beat_ids"][0]}
    return {
        "project_id": project["project_id"],
        "quality_mode": project["prompts"].get("quality_mode", "standard"),
        "total_scenes": len(scenes),
        "total_visual_slots": len(scenes),
        "target_unique_shots": len(shots),
        "actual_unique_shots": len(shots),
        "planning_source": "narration_beats.json",
        "scene_groups": scene_groups,
        "shots": shots,
        "scene_to_shot": scene_to_shot,
        "visual_slot_to_shot": {},
    }


def normalize_plan(raw_plan: dict[str, Any], quality_mode: str) -> dict[str, Any]:
    raw_plan["quality_mode"] = quality_mode
    raw_plan.setdefault("visual_slot_to_shot", {})
    return raw_plan


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
    allocation_path = Path(project["planning"].get("visual_allocation_plan_path", ""))
    continuity_path = Path(project["planning"]["continuity_map_json_path"])
    visual_bible_path = Path(project["prompts"]["visual_bible_path"])
    output_path = Path(project["prompts"]["visual_shot_plan_path"])
    quality_mode = args.quality_mode or project["prompts"].get("quality_mode", "standard")

    scene_plan = load_json(scene_plan_path)
    beats_payload = load_json(narration_beats_path)
    continuity = load_json(continuity_path) if continuity_path.exists() else {}
    visual_bible = load_json(visual_bible_path) if visual_bible_path.exists() else {}

    if args.input_json:
        plan = normalize_plan(load_json(Path(args.input_json).resolve()), quality_mode)
    elif allocation_path.exists():
        allocation = load_json(allocation_path)
        plan = build_from_visual_allocation(project, allocation, continuity, visual_bible)
        plan["quality_mode"] = quality_mode
    else:
        plan = build_default_plan(project, scene_plan, beats_payload, continuity, visual_bible)
        plan["quality_mode"] = quality_mode

    save_json(output_path, plan)
    project["prompts"]["quality_mode"] = quality_mode
    project["prompts"]["visual_shot_plan_path"] = str(output_path)
    project["prompts"]["visual_shot_plan_status"] = "planned"
    project["current_stage"] = "build_frame_briefs"
    save_project(project_json, project)
    print(output_path)


if __name__ == "__main__":
    main()
