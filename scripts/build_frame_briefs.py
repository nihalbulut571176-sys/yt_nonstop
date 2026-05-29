import argparse
import json
from pathlib import Path
from typing import Any

from pipeline_contracts import FrameBrief, build_frame_id, build_shot_id, dedupe_strings, request_spec_from_project, stable_hash, write_csv
from project_pipeline_utils import load_json, load_project, save_json, save_project


NON_GENERATIVE_DECISIONS = {"hold_previous", "continuation_motion"}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def choose_style_meta(scene: dict, index: int, slot: dict | None = None) -> dict:
    slot = slot or {}
    scales = ["wide", "medium", "close-up", "macro"]
    angles = ["eye-level", "low angle", "high angle", "over-the-shoulder", "top-down"]
    scene_types = ["place", "detail", "human", "process", "consequence"]
    lighting = ["motivated", "screen glow", "cold practical", "warm interior"]
    density = ["clean", "layered", "dense", "forensic"]
    motion = ["slow_push_in", "static_tension", "pan_right", "slow_pull_out"]
    emotion = ["curiosity", "pressure", "tension", "discovery", "aftermath"]
    slot_type = clean_text(slot.get("slot_type")).lower()
    if slot_type in {"detail_insert", "evidence_insert"}:
        default_scale = "close-up"
        default_scene_type = "detail"
    elif slot_type == "establishing_shot":
        default_scale = "wide"
        default_scene_type = "place"
    elif slot_type == "reaction_shot":
        default_scale = "medium"
        default_scene_type = "human"
    else:
        default_scale = scales[(index - 1) % len(scales)]
        default_scene_type = scene_types[(index - 1) % len(scene_types)]
    return {
        "scale": slot.get("scale") or scene.get("scale") or default_scale,
        "angle": slot.get("angle") or scene.get("angle") or angles[(index - 1) % len(angles)],
        "scene_type": slot.get("scene_type") or default_scene_type,
        "lighting": slot.get("lighting") or scene.get("lighting_family") or lighting[(index - 1) % len(lighting)],
        "emotional_energy": slot.get("emotional_energy") or emotion[(index - 1) % len(emotion)],
        "visual_density": slot.get("density") or scene.get("density") or density[(index - 1) % len(density)],
        "motion_treatment": slot.get("motion_treatment") or ("static_tension" if slot.get("generation_decision") in NON_GENERATIVE_DECISIONS else motion[(index - 1) % len(motion)]),
    }


def infer_subject_fields(scene: dict, storyboard_item: dict, continuity_segment: dict, slot: dict | None = None, beat: dict | None = None) -> dict:
    slot = slot or {}
    beat = beat or {}
    mentioned_subject_ids = list(
        dict.fromkeys(
            slot.get("primary_entity_ids")
            or beat.get("entity_mentions", [])
            or scene.get("mentioned_subject_ids")
            or continuity_segment.get("active_entities", [])
            or []
        )
    )
    primary_subject_id = slot.get("primary_subject_id") or scene.get("primary_subject_id")
    if not primary_subject_id and mentioned_subject_ids:
        primary_subject_id = mentioned_subject_ids[0]

    visible_subject_ids = list(slot.get("visible_subject_ids") or scene.get("visible_subject_ids") or [])
    if not visible_subject_ids and primary_subject_id:
        visual_role = str(storyboard_item.get("visual_role", "")).lower()
        scene_type = str(scene.get("scene_type", "")).lower()
        slot_type = str(slot.get("slot_type", "")).lower()
        primary_subject = str(scene.get("primary_subject", "")).strip()
        should_show = any(
            marker in f"{visual_role} {scene_type} {slot_type} {primary_subject}".lower()
            for marker in ("human", "portrait", "operator", "guard", "worker", "customer", "person", "character", "reaction")
        ) or bool(primary_subject)
        if should_show:
            visible_subject_ids = [primary_subject_id]

    subject_ids = list(dict.fromkeys(scene.get("subject_ids") or mentioned_subject_ids or visible_subject_ids))
    subject_visible = bool(scene.get("subject_visible")) or bool(visible_subject_ids)
    continuity_strength = str(scene.get("subject_continuity_strength") or ("medium" if subject_visible and primary_subject_id else "none"))

    return {
        "mentioned_subject_ids": mentioned_subject_ids,
        "visible_subject_ids": visible_subject_ids,
        "subject_ids": subject_ids,
        "primary_subject_id": primary_subject_id,
        "subject_visible": subject_visible,
        "subject_continuity_strength": continuity_strength,
    }


def legacy_prompt_package_item(scene: dict, frame_brief: dict) -> dict:
    item = dict(scene)
    for key, value in frame_brief.items():
        item[key] = value
    item["voice_text"] = frame_brief.get("srt_text", scene.get("voice_text", ""))
    item["start"] = frame_brief.get("timeline_in", scene.get("start"))
    item["end"] = frame_brief.get("timeline_out", scene.get("end"))
    item["duration"] = frame_brief.get("duration_sec", scene.get("duration"))
    return item


def derive_variant_count(priority: str, decision: str, entity_locks: list[dict], slot: dict) -> tuple[str, bool, int]:
    priority = clean_text(priority or "low").lower() or "low"
    if decision in NON_GENERATIVE_DECISIONS:
        return "reuse", False, 0
    required_identity = any(
        entity.get("reference_policy") == "required" or entity.get("identity_lock") == "required"
        for entity in entity_locks
    )
    explicit = slot.get("variant_count")
    if explicit is not None:
        count = int(explicit or 0)
        if priority == "high" or count >= 3:
            return "hero", True, max(1, count)
        if priority == "medium":
            return "supporting", False, max(1, count)
        return "bridge", False, max(1, count)
    if priority == "high" and required_identity:
        return "hero", True, 3
    if priority == "high":
        return "hero", True, 2
    if priority == "medium":
        return "supporting", False, 1
    return "bridge", False, 1


def load_visual_slots(project: dict) -> tuple[list[dict], dict[str, dict]]:
    path = Path(project["planning"].get("visual_allocation_plan_path", ""))
    if not path.exists():
        return [], {}
    payload = load_json(path)
    slots = payload.get("visual_slots", [])
    return slots, {slot.get("visual_slot_id"): slot for slot in slots if slot.get("visual_slot_id")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    request_spec = request_spec_from_project(project)
    storyboard_path = Path(project["planning"]["storyboard_path"])
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])

    if request_spec.is_sequence and not request_spec.skip_storyboard_allowed and not storyboard_path.exists():
        raise RuntimeError("Sequence workflow requires storyboard output before frame briefs can be built")

    scene_plan = load_json(scene_plan_path)
    original_scenes = list(scene_plan.get("scenes", []))
    source_scene_by_id = {scene["scene_id"]: scene for scene in original_scenes if scene.get("scene_id")}
    storyboard = load_json(storyboard_path) if storyboard_path.exists() else {"items": []}
    storyboard_by_segment = {int(item["segment_id"]): item for item in storyboard.get("items", []) if item.get("segment_id") is not None}
    continuity_path = Path(project["planning"]["continuity_map_json_path"])
    continuity = load_json(continuity_path) if continuity_path.exists() else {}
    continuity_by_segment = continuity.get("segment_entity_map", {})
    narration_beats_path = Path(project["planning"]["narration_beats_path"])
    narration_beats = load_json(narration_beats_path).get("beats", []) if narration_beats_path.exists() else []
    beats_by_scene = {beat.get("scene_id"): beat for beat in narration_beats if beat.get("scene_id")}
    beats_by_id = {beat.get("beat_id"): beat for beat in narration_beats if beat.get("beat_id")}
    subject_registry_path = Path(project["prompts"]["subject_registry_path"])
    subject_registry = load_json(subject_registry_path).get("subjects", []) if subject_registry_path.exists() else []
    subject_by_id = {item["subject_id"]: item for item in subject_registry if item.get("subject_id")}
    visual_shot_plan_path = Path(project["prompts"]["visual_shot_plan_path"])
    if request_spec.is_sequence and not visual_shot_plan_path.exists():
        raise RuntimeError("Sequence workflow requires visual_shot_plan output before frame briefs can be built")
    visual_shot_plan = load_json(visual_shot_plan_path) if visual_shot_plan_path.exists() else {}
    visual_slot_to_shot = visual_shot_plan.get("visual_slot_to_shot", {})
    scene_to_shot = visual_shot_plan.get("scene_to_shot", {})
    shots_by_id = {item["shot_id"]: item for item in visual_shot_plan.get("shots", []) if item.get("shot_id")}
    visual_slots, _slots_by_id = load_visual_slots(project)

    # Legacy fallback: one visual slot per source scene when no visual allocation exists.
    if not visual_slots:
        for index, scene in enumerate(original_scenes, start=1):
            beat = beats_by_scene.get(scene["scene_id"], {})
            visual_slots.append(
                {
                    "visual_slot_id": scene.get("scene_id"),
                    "beat_ids": [beat.get("beat_id") or scene.get("beat_id") or f"beat_{index:04d}"],
                    "scene_ids": [scene["scene_id"]],
                    "source_scene_id": scene["scene_id"],
                    "start": scene["start"],
                    "end": scene["end"],
                    "duration": scene["duration"],
                    "slot_type": "explanation_visual",
                    "visual_function": beat.get("beat_role") or scene.get("visual_function") or "explain",
                    "must_show": beat.get("must_visualize", []) or scene.get("must_show", []) or [scene.get("voice_text", "")],
                    "visualized_claim": beat.get("spoken_claim") or scene.get("visualized_claim") or scene.get("voice_text", ""),
                    "generation_decision": "new_image",
                    "priority": beat.get("visual_priority", "low"),
                    "variant_count": scene.get("variant_count", 1),
                }
            )

    frame_briefs = []
    legacy_items = []
    visual_scene_records = []
    for index, slot in enumerate(visual_slots, start=1):
        source_scene_id = clean_text(slot.get("source_scene_id") or (slot.get("scene_ids") or [""])[0])
        source_scene = dict(source_scene_by_id.get(source_scene_id, {}))
        if not source_scene:
            raise RuntimeError(f"Visual slot {slot.get('visual_slot_id')} points to unknown source_scene_id {source_scene_id}")
        source_segment_id = int(source_scene.get("source_segment_id") or index)
        storyboard_item = storyboard_by_segment.get(source_segment_id, {})
        beat_ids = [clean_text(item) for item in slot.get("beat_ids", []) if clean_text(item)]
        primary_beat = beats_by_id.get(beat_ids[0]) if beat_ids else beats_by_scene.get(source_scene_id, {})
        style_meta = choose_style_meta(source_scene, index, slot)
        visual_slot_id = clean_text(slot.get("visual_slot_id") or f"VS{index:04d}")
        effective_scene_id = visual_slot_id
        shot_mapping = visual_slot_to_shot.get(visual_slot_id) or scene_to_shot.get(source_scene_id, {})
        shot = shots_by_id.get(shot_mapping.get("shot_id") or slot.get("shot_id") or source_scene.get("shot_id"), {})
        subject_meta = infer_subject_fields(
            source_scene,
            storyboard_item,
            continuity_by_segment.get(str(source_segment_id), {}),
            slot=slot,
            beat=primary_beat,
        )
        continuity_tags = list(
            dict.fromkeys(
                [
                    *continuity_by_segment.get(str(source_segment_id), {}).get("active_entities", []),
                    source_scene.get("environment", ""),
                    source_scene.get("primary_subject", ""),
                    storyboard_item.get("visual_role", ""),
                    shot.get("film_block_id", ""),
                ]
            )
        )
        continuity_tags = [tag for tag in continuity_tags if tag]
        entity_locks = []
        lock_ids = slot.get("primary_entity_ids") or primary_beat.get("entity_mentions", []) or subject_meta["visible_subject_ids"] or subject_meta["mentioned_subject_ids"]
        for subject_id in dedupe_strings([str(item) for item in lock_ids]):
            profile = subject_by_id.get(subject_id, {})
            entity_locks.append(
                {
                    "entity_id": subject_id,
                    "identity_lock": "required" if profile.get("reference_policy") == "required" else "optional",
                    "reference_policy": profile.get("reference_policy", "optional"),
                    "reference_ids": profile.get("reference_asset_ids", []),
                }
            )
        decision = clean_text(slot.get("generation_decision") or shot.get("generation_decision") or shot.get("generation_mode") or "new_image").lower()
        beat_priority, key_beat, variant_count = derive_variant_count(clean_text(slot.get("priority") or primary_beat.get("visual_priority") or "low"), decision, entity_locks, slot)
        shot_must_show = [str(item) for item in (shot.get("must_show") or slot.get("must_show") or primary_beat.get("must_visualize", [])) if str(item).strip()]
        screen_action = str(slot.get("visualized_claim") or storyboard_item.get("on_screen_action") or source_scene.get("visual_idea") or (shot_must_show[0] if shot_must_show else source_scene["voice_text"]))
        start = float(slot.get("start", source_scene["start"]) or source_scene["start"])
        end = float(slot.get("end", source_scene["end"]) or source_scene["end"])
        duration = max(0.001, end - start)
        voice_text = " ".join([clean_text(beats_by_id.get(beat_id, {}).get("voice_text")) for beat_id in beat_ids if beats_by_id.get(beat_id)]) or clean_text(source_scene.get("voice_text"))
        frame_brief = FrameBrief(
            frame_id=build_frame_id(index),
            beat_id=beat_ids[0] if beat_ids else str(primary_beat.get("beat_id") or source_scene.get("beat_id") or f"beat_{index:04d}"),
            scene_id=effective_scene_id,
            segment_id=f"B{source_segment_id:02d}",
            storyboard_id=storyboard_item.get("storyboard_id", f"SB{source_segment_id:04d}"),
            shot_id=str(shot_mapping.get("shot_id") or shot.get("shot_id") or build_shot_id(index)),
            semantic_unit_id=source_scene.get("semantic_unit_id") or storyboard_item.get("semantic_unit_id", f"SU{source_segment_id:04d}"),
            visual_role=shot.get("visual_function") or slot.get("visual_function") or storyboard_item.get("visual_role", source_scene.get("visual_function", "explain")),
            shot_function=shot.get("visual_function") or slot.get("visual_function") or storyboard_item.get("shot_function", source_scene.get("narrative_purpose", "explain")),
            source_stage=storyboard_item.get("source_stage", "build_frame_briefs"),
            timeline_in=start,
            timeline_out=end,
            duration_sec=duration,
            srt_indices=str(source_scene.get("srt_indices") or source_segment_id),
            srt_text=voice_text,
            scene_anchor=str(source_scene.get("main_subject") or source_scene.get("scene_meaning") or voice_text),
            screen_action=screen_action,
            plan=str(slot.get("shot_design") or source_scene.get("composition") or storyboard_item.get("composition_progression") or shot.get("shot_type") or "documentary still"),
            camera_storyboard=str(storyboard_item.get("camera_storyboard") or shot.get("camera") or slot.get("camera") or source_scene.get("camera") or "documentary framing"),
            visual_slot_id=visual_slot_id,
            source_scene_id=source_scene_id,
            source_beat_ids=beat_ids,
            generation_decision=decision,
            slot_type=str(slot.get("slot_type") or shot.get("slot_type") or "explanation_visual"),
            generation_mode=decision,
            source_shot_id=str(shot_mapping.get("source_shot_id") or shot.get("source_shot_id") or slot.get("source_visual_slot_id") or ""),
            variation_note=str(shot_mapping.get("variation_note") or slot.get("reason") or ""),
            shot_type=str(shot.get("shot_type") or slot.get("shot_design") or "medium shot"),
            transition_in=str(shot.get("transition_in") or slot.get("transition_in") or "cut"),
            transition_out=str(shot.get("transition_out") or slot.get("transition_out") or "cut_on_phrase_end"),
            visualized_claim=str(slot.get("visualized_claim") or primary_beat.get("spoken_claim") or source_scene.get("visual_goal") or source_scene.get("scene_meaning") or voice_text),
            must_show=shot_must_show,
            entity_locks=entity_locks,
            camera_rule=str(shot.get("camera") or slot.get("camera") or source_scene.get("camera") or storyboard_item.get("camera_storyboard") or "documentary framing"),
            style_rule=str(project["prompts"].get("global_style_summary") or project["prompts"]["style_preset"]),
            negative_constraints=["no logos", "no readable text", "no fake UI words"],
            film_block_id=str(shot.get("film_block_id") or slot.get("film_block_id") or source_scene.get("global_scene_id") or f"block_{index:04d}"),
            beat_priority=beat_priority,
            key_beat=key_beat,
            variant_count=variant_count,
            mentioned_subject_ids=subject_meta["mentioned_subject_ids"],
            visible_subject_ids=subject_meta["visible_subject_ids"],
            subject_ids=subject_meta["subject_ids"],
            primary_subject_id=subject_meta["primary_subject_id"],
            subject_visible=subject_meta["subject_visible"],
            subject_continuity_strength=subject_meta["subject_continuity_strength"],
            reference_bindings=list(source_scene.get("reference_bindings", [])),
            continuity_tags=continuity_tags,
            global_style=str(project["prompts"].get("global_style_summary") or project["prompts"]["style_preset"]),
            hard_constraints=["no logos", "no readable text", "no fake UI words"],
            scale=style_meta["scale"],
            angle=style_meta["angle"],
            scene_type=style_meta["scene_type"],
            lighting=style_meta["lighting"],
            emotional_energy=style_meta["emotional_energy"],
            visual_density=style_meta["visual_density"],
            motion_treatment=style_meta["motion_treatment"],
            prompt_contract_version=project["workflow"]["prompt_contract_version"],
            llm_model_id=project["prompts"]["authoring_model"],
            generation_lock_version=project["workflow"]["generation_lock_version"],
        )
        frame_dict = frame_brief.__dict__
        frame_dict["voice_text"] = frame_dict.get("srt_text", "")
        frame_dict["start"] = frame_dict.get("timeline_in")
        frame_dict["end"] = frame_dict.get("timeline_out")
        frame_dict["duration"] = frame_dict.get("duration_sec")
        frame_dict["frame_brief_hash"] = stable_hash(
            {
                "frame_id": frame_dict["frame_id"],
                "scene_id": frame_dict["scene_id"],
                "visual_slot_id": frame_dict["visual_slot_id"],
                "timeline_in": frame_dict["timeline_in"],
                "timeline_out": frame_dict["timeline_out"],
                "srt_text": frame_dict["srt_text"],
                "storyboard_id": frame_dict["storyboard_id"],
                "prompt_contract_version": frame_dict["prompt_contract_version"],
            }
        )
        frame_briefs.append(frame_dict)
        visual_scene = dict(source_scene)
        visual_scene.update(
            {
                "source_scene_id": source_scene_id,
                "source_beat_ids": beat_ids,
                "visual_slot_id": visual_slot_id,
                "scene_id": effective_scene_id,
                "shot_index": index,
                "frame_id": frame_dict["frame_id"],
                "beat_id": frame_dict["beat_id"],
                "start": start,
                "end": end,
                "duration": duration,
                "voice_text": voice_text,
                "storyboard_id": frame_dict["storyboard_id"],
                "semantic_unit_id": frame_dict["semantic_unit_id"],
                "shot_id": frame_dict["shot_id"],
                "generation_mode": frame_dict["generation_mode"],
                "generation_decision": frame_dict["generation_decision"],
                "slot_type": frame_dict["slot_type"],
                "source_shot_id": frame_dict["source_shot_id"],
                "variation_note": frame_dict["variation_note"],
                "shot_type": frame_dict["shot_type"],
                "transition_in": frame_dict["transition_in"],
                "transition_out": frame_dict["transition_out"],
                "visual_role": frame_dict["visual_role"],
                "shot_function": frame_dict["shot_function"],
                "mentioned_subject_ids": frame_dict["mentioned_subject_ids"],
                "visible_subject_ids": frame_dict["visible_subject_ids"],
                "subject_ids": frame_dict["subject_ids"],
                "primary_subject_id": frame_dict["primary_subject_id"],
                "subject_visible": frame_dict["subject_visible"],
                "subject_continuity_strength": frame_dict["subject_continuity_strength"],
                "reference_bindings": frame_dict["reference_bindings"],
                "visualized_claim": frame_dict["visualized_claim"],
                "must_show": frame_dict["must_show"],
                "entity_locks": frame_dict["entity_locks"],
                "film_block_id": frame_dict["film_block_id"],
                "beat_priority": frame_dict["beat_priority"],
                "key_beat": frame_dict["key_beat"],
                "variant_count": frame_dict["variant_count"],
            }
        )
        visual_scene_records.append(visual_scene)
        legacy_items.append(legacy_prompt_package_item(visual_scene, frame_dict))

    frame_briefs_json_path = Path(project["planning"]["frame_briefs_json_path"])
    frame_briefs_csv_path = Path(project["planning"]["frame_briefs_csv_path"])
    save_json(frame_briefs_json_path, frame_briefs)
    write_csv(frame_briefs_csv_path, frame_briefs)
    scene_plan.setdefault("source_scenes", original_scenes)
    scene_plan["scenes"] = visual_scene_records
    scene_plan["visual_allocation_applied"] = True
    scene_plan["visual_slot_count"] = len(visual_scene_records)
    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    prompt_package = {
        "project_id": project["project_id"],
        "profile_id": project["profile_id"],
        "schema_version": project["schema_version"],
        "source_language": project["meta"].get("language", "auto"),
        "prompt_language": project["prompts"]["prompt_language"],
        "style_preset": project["prompts"]["style_preset"],
        "global_style_summary": project["prompts"].get("global_style_summary"),
        "canonical_scene_plan_path": str(scene_plan_path),
        "frame_briefs_path": str(frame_briefs_json_path),
        "scene_count": len(legacy_items),
        "visual_slot_count": len(legacy_items),
        "items": legacy_items,
    }
    save_json(Path(project["prompts"]["prompt_package_path"]), prompt_package)

    project["planning"]["status"] = "frame_briefs_built"
    project["prompts"]["status"] = "package_built"
    project["current_stage"] = "attach_reference_assets"
    save_project(project_json, project)
    print(frame_briefs_json_path)


if __name__ == "__main__":
    main()
