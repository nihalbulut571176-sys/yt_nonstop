import argparse
import json
from pathlib import Path

from pipeline_contracts import FrameBrief, build_frame_id, build_shot_id, request_spec_from_project, stable_hash, write_csv
from project_pipeline_utils import load_json, load_project, save_json, save_project


def choose_style_meta(scene: dict, index: int) -> dict:
    scales = ["wide", "medium", "close-up", "macro"]
    angles = ["eye-level", "low angle", "high angle", "over-the-shoulder", "top-down"]
    scene_types = ["place", "detail", "human", "process", "consequence"]
    lighting = ["motivated", "screen glow", "cold practical", "warm interior"]
    density = ["clean", "layered", "dense", "forensic"]
    motion = ["slow_push_in", "static_tension", "pan_right", "slow_pull_out"]
    emotion = ["curiosity", "pressure", "tension", "discovery", "aftermath"]
    return {
        "scale": scene.get("scale") or scales[(index - 1) % len(scales)],
        "angle": scene.get("angle") or angles[(index - 1) % len(angles)],
        "scene_type": scene_types[(index - 1) % len(scene_types)],
        "lighting": scene.get("lighting_family") or lighting[(index - 1) % len(lighting)],
        "emotional_energy": emotion[(index - 1) % len(emotion)],
        "visual_density": scene.get("density") or density[(index - 1) % len(density)],
        "motion_treatment": motion[(index - 1) % len(motion)],
    }


def legacy_prompt_package_item(scene: dict, frame_brief: dict) -> dict:
    item = dict(scene)
    item["frame_id"] = frame_brief["frame_id"]
    item["storyboard_id"] = frame_brief["storyboard_id"]
    item["semantic_unit_id"] = frame_brief["semantic_unit_id"]
    item["shot_id"] = frame_brief["shot_id"]
    item["visual_role"] = frame_brief["visual_role"]
    item["shot_function"] = frame_brief["shot_function"]
    item["source_stage"] = frame_brief["source_stage"]
    item["screen_action"] = frame_brief["screen_action"]
    item["camera_storyboard"] = frame_brief["camera_storyboard"]
    item["continuity_tags"] = frame_brief["continuity_tags"]
    item["hard_constraints"] = frame_brief["hard_constraints"]
    item["frame_brief_hash"] = frame_brief["frame_brief_hash"]
    item["prompt_contract_version"] = frame_brief["prompt_contract_version"]
    item["generation_lock_version"] = frame_brief["generation_lock_version"]
    item["llm_model_id"] = frame_brief["llm_model_id"]
    item["llm_prompt_template_version"] = frame_brief["llm_prompt_template_version"]
    item["timeline_in"] = frame_brief["timeline_in"]
    item["timeline_out"] = frame_brief["timeline_out"]
    item["duration_sec"] = frame_brief["duration_sec"]
    item["srt_indices"] = frame_brief["srt_indices"]
    item["srt_text"] = frame_brief["srt_text"]
    item["plan"] = frame_brief["plan"]
    item["global_style"] = frame_brief["global_style"]
    return item


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
    storyboard = load_json(storyboard_path) if storyboard_path.exists() else {"items": []}
    storyboard_by_segment = {int(item["segment_id"]): item for item in storyboard.get("items", [])}
    continuity_path = Path(project["planning"]["continuity_map_json_path"])
    continuity = load_json(continuity_path) if continuity_path.exists() else {}
    continuity_by_segment = continuity.get("segment_entity_map", {})

    frame_briefs = []
    legacy_items = []
    for index, scene in enumerate(scene_plan.get("scenes", []), start=1):
        storyboard_item = storyboard_by_segment.get(int(scene["source_segment_id"]), {})
        style_meta = choose_style_meta(scene, index)
        continuity_tags = list(
            dict.fromkeys(
                [
                    *continuity_by_segment.get(str(scene["source_segment_id"]), {}).get("active_entities", []),
                    scene.get("environment", ""),
                    scene.get("primary_subject", ""),
                    storyboard_item.get("visual_role", ""),
                ]
            )
        )
        continuity_tags = [tag for tag in continuity_tags if tag]
        frame_brief = FrameBrief(
            frame_id=build_frame_id(index),
            scene_id=scene["scene_id"],
            segment_id=f"B{int(scene['source_segment_id']):02d}",
            storyboard_id=storyboard_item.get("storyboard_id", f"SB{int(scene['source_segment_id']):04d}"),
            shot_id=scene.get("shot_id") or build_shot_id(index),
            semantic_unit_id=scene.get("semantic_unit_id") or storyboard_item.get("semantic_unit_id", f"SU{int(scene['source_segment_id']):04d}"),
            visual_role=storyboard_item.get("visual_role", scene.get("visual_function", "explain")),
            shot_function=storyboard_item.get("shot_function", scene.get("narrative_purpose", "explain")),
            source_stage=storyboard_item.get("source_stage", "build_frame_briefs"),
            timeline_in=float(scene["start"]),
            timeline_out=float(scene["end"]),
            duration_sec=float(scene["duration"]),
            srt_indices=str(scene.get("srt_indices") or scene["source_segment_id"]),
            srt_text=str(scene["voice_text"]),
            scene_anchor=str(scene.get("main_subject") or scene.get("scene_meaning") or scene["voice_text"]),
            screen_action=str(storyboard_item.get("on_screen_action") or scene.get("visual_idea") or scene["voice_text"]),
            plan=str(scene.get("composition") or storyboard_item.get("composition_progression") or "documentary still"),
            camera_storyboard=str(storyboard_item.get("camera_storyboard") or scene.get("camera") or "documentary framing"),
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
        frame_dict["frame_brief_hash"] = stable_hash(
            {
                "frame_id": frame_dict["frame_id"],
                "scene_id": frame_dict["scene_id"],
                "timeline_in": frame_dict["timeline_in"],
                "timeline_out": frame_dict["timeline_out"],
                "srt_text": frame_dict["srt_text"],
                "storyboard_id": frame_dict["storyboard_id"],
                "prompt_contract_version": frame_dict["prompt_contract_version"],
            }
        )
        frame_briefs.append(frame_dict)
        scene["frame_id"] = frame_dict["frame_id"]
        scene["storyboard_id"] = frame_dict["storyboard_id"]
        scene["semantic_unit_id"] = frame_dict["semantic_unit_id"]
        scene["shot_id"] = frame_dict["shot_id"]
        scene["visual_role"] = frame_dict["visual_role"]
        scene["shot_function"] = frame_dict["shot_function"]
        legacy_items.append(legacy_prompt_package_item(scene, frame_dict))

    frame_briefs_json_path = Path(project["planning"]["frame_briefs_json_path"])
    frame_briefs_csv_path = Path(project["planning"]["frame_briefs_csv_path"])
    save_json(frame_briefs_json_path, frame_briefs)
    write_csv(frame_briefs_csv_path, frame_briefs)
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
        "items": legacy_items,
    }
    save_json(Path(project["prompts"]["prompt_package_path"]), prompt_package)

    project["planning"]["status"] = "frame_briefs_built"
    project["prompts"]["status"] = "package_built"
    project["current_stage"] = "generate_fastgen_prompt_drafts"
    save_project(project_json, project)
    print(frame_briefs_json_path)


if __name__ == "__main__":
    main()
