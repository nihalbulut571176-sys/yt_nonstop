import argparse
import json
from pathlib import Path
from typing import Any

from apply_review_decisions import apply_review_decisions_to_project
from motion_engine import derive_motion_metadata
from project_pipeline_utils import load_project, save_project
from yt_nonstop.review.policy import selection_is_render_blocking, selection_is_timeline_eligible



def safe_ffconcat_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", r"'\''")


def load_json_if_exists(path: Path, fallback: Any) -> Any:
    if not path or not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def partial_pilot_mode(project: dict[str, Any]) -> bool:
    manifest_path = Path(project["images"].get("run_manifest_path", ""))
    if manifest_path.exists():
        payload = load_json_if_exists(manifest_path, {})
        if isinstance(payload, dict) and (payload.get("partial_pilot") or payload.get("limited_pilot")):
            return True
    return str(project.get("images", {}).get("status", "")).strip().lower() in {"partial", "pilot_partial"}


def resolve_scene_image(scene: dict, selected_row: dict, montage_row: dict, previous_image: str | None) -> str:
    image_path_str = (
        scene.get("render_asset_path")
        or scene.get("still_image_path")
        or selected_row.get("normalized_image_path")
        or selected_row.get("selected_image_path")
        or selected_row.get("image_path")
        or (montage_row or {}).get("asset_image_path")
    )
    generation_decision = str(scene.get("generation_decision") or scene.get("generation_mode") or "").strip()
    if not image_path_str and generation_decision in {"hold_previous", "continuation_motion"} and previous_image:
        image_path_str = previous_image
    return str(image_path_str or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)

    review_decisions_path = Path(project.get("qc", {}).get("review_decisions_path", ""))
    if review_decisions_path.exists():
        apply_review_decisions_to_project(project_json)
        project = load_project(project_json)

    montage_map_path = Path(project["exports"]["montage_timing_map_json_path"])
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    scene_plan_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    scenes = scene_plan.get("scenes", [])
    if not scenes:
        raise RuntimeError(f"No scenes found in {scene_plan_path}")

    montage_rows = load_json_if_exists(montage_map_path, [])
    montage_by_frame = {row["frame_id"]: row for row in montage_rows if isinstance(row, dict) and row.get("frame_id")}
    selected_manifest_path = Path(project["images"].get("selected_images_manifest_path", ""))
    selected_manifest = load_json_if_exists(selected_manifest_path, {})
    selected_by_scene = {
        row["scene_id"]: row
        for row in selected_manifest.get("selected_images", [])
        if isinstance(row, dict) and row.get("scene_id")
    }

    renders_dir = Path(project["meta"]["project_root"]) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ffconcat_path = renders_dir / "timeline.ffconcat"
    timeline_json_path = renders_dir / "slideshow_timeline.json"
    edit_decision_list_path = Path(project["render"]["edit_decision_list_path"])
    audio_duration = float(project["inputs"].get("audio_duration_seconds") or 0)
    if audio_duration <= 0:
        audio_duration = float(scenes[-1]["end"])

    prepared_scenes = []
    skipped_by_review = []
    skipped_unavailable = []
    previous_image: str | None = None
    allow_partial_pilot = partial_pilot_mode(project)

    for index, scene in enumerate(scenes):
        montage_row = montage_by_frame.get(scene.get("frame_id", ""), {})
        selected_row = selected_by_scene.get(scene["scene_id"], {})
        selection_status = str(selected_row.get("selection_status", "use")).strip()
        human_review_status = str(selected_row.get("human_review_status", "")).strip()
        if selected_row and selection_is_render_blocking(project, selected_row):
            skipped_by_review.append(
                {
                    "scene_id": scene["scene_id"],
                    "frame_id": scene.get("frame_id", ""),
                    "beat_id": scene.get("beat_id", ""),
                    "visual_slot_id": scene.get("visual_slot_id", ""),
                    "selection_status": selection_status,
                    "human_review_status": human_review_status,
                    "reason": selected_row.get("render_exclusion_reason") or "human_review_excluded",
                }
            )
            continue
        if selected_row and not selection_is_timeline_eligible(project, selected_row):
            raise RuntimeError(f"Scene {scene['scene_id']} selected image is not timeline-eligible: {selection_status}")

        image_path_str = resolve_scene_image(scene, selected_row, montage_row, previous_image)
        if not image_path_str:
            if allow_partial_pilot:
                skipped_unavailable.append(
                    {
                        "scene_id": scene["scene_id"],
                        "frame_id": scene.get("frame_id", ""),
                        "visual_slot_id": scene.get("visual_slot_id", ""),
                        "reason": "pilot_image_not_generated",
                    }
                )
                continue
            raise FileNotFoundError(f"Scene {scene.get('scene_id')} has no still image path")
        image_path = Path(image_path_str)
        if not image_path.exists():
            if allow_partial_pilot:
                skipped_unavailable.append(
                    {
                        "scene_id": scene["scene_id"],
                        "frame_id": scene.get("frame_id", ""),
                        "visual_slot_id": scene.get("visual_slot_id", ""),
                        "reason": f"pilot_image_missing:{image_path}",
                    }
                )
                continue
            raise FileNotFoundError(f"Missing image for scene {scene.get('scene_id')}: {image_path}")
        previous_image = str(image_path)
        prepared_scenes.append(
            {
                "source_index": index,
                "scene": scene,
                "montage_row": montage_row,
                "selected_row": selected_row,
                "image_path": image_path,
            }
        )

    if not prepared_scenes:
        raise RuntimeError("No timeline-eligible scenes remain after human review decisions; selected images are not timeline-eligible")

    ffconcat_lines = ["ffconcat version 1.0"]
    timeline = []
    edit_decision_list = []
    previous_scene_for_motion = None

    for prepared_index, item in enumerate(prepared_scenes):
        scene = item["scene"]
        montage_row = item["montage_row"]
        image_path = item["image_path"]
        source_start = float(scene["start"])
        render_start = 0.0 if prepared_index == 0 and source_start > 0 else source_start
        speech_end = float(scene["end"])
        if prepared_index + 1 < len(prepared_scenes):
            next_start = float(prepared_scenes[prepared_index + 1]["scene"]["start"])
        else:
            next_start = audio_duration
        display_end = max(next_start, speech_end)
        if prepared_index + 1 == len(prepared_scenes):
            display_end = max(audio_duration, speech_end)
        duration = max(0.001, display_end - render_start)
        motion_meta = derive_motion_metadata(scene, previous_scene_for_motion)
        previous_scene_for_motion = scene

        ffconcat_lines.append(f"file '{safe_ffconcat_path(image_path)}'")
        ffconcat_lines.append(f"duration {duration:.6f}")
        common = {
            "frame_id": scene.get("frame_id", ""),
            "beat_id": scene.get("beat_id", ""),
            "scene_id": scene["scene_id"],
            "source_scene_id": scene.get("source_scene_id", scene["scene_id"]),
            "visual_slot_id": scene.get("visual_slot_id", ""),
            "generation_decision": scene.get("generation_decision", scene.get("generation_mode", "")),
            "slot_type": scene.get("slot_type", ""),
            "visual_function": scene.get("visual_function", scene.get("shot_function", scene.get("visual_role", ""))),
            "film_block_id": scene.get("film_block_id", ""),
            "start": render_start,
            "source_start": source_start,
            "end": display_end,
            "duration": duration,
            "speech_end": speech_end,
            "voice_text": scene.get("voice_text", ""),
            **motion_meta,
        }
        timeline.append(
            {
                **common,
                "shot_index": scene.get("shot_index", prepared_index + 1),
                "image": str(image_path),
                "srt_indices": (montage_row or {}).get("srt_indices", scene.get("srt_indices", "")),
                "screen_action": (montage_row or {}).get("screen_action", ""),
                "motion_id": scene.get("motion_id", ""),
                "motion_plan": scene.get("motion_plan", {}),
            }
        )
        edit_decision_list.append(
            {
                **common,
                "image_path": str(image_path),
                "motion": motion_meta["motion_type"],
                "transition_in": scene.get("transition_in", "cut"),
                "transition_out": scene.get("transition_out", "cut_on_phrase_end"),
                "transition_style": motion_meta["transition_style"],
                "visualized_claim": scene.get("visualized_claim", ""),
                "sync_rule": "frame starts exactly at beat start",
            }
        )

    last_image = Path(timeline[-1]["image"])
    ffconcat_lines.append(f"file '{safe_ffconcat_path(last_image)}'")

    ffconcat_path.write_text("\n".join(ffconcat_lines) + "\n", encoding="utf-8")
    timeline_json_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    edit_decision_list_path.write_text(
        json.dumps(
            {
                "project_id": project["project_id"],
                "edl": edit_decision_list,
                "skipped_by_human_review": skipped_by_review,
                "skipped_by_review": skipped_by_review,
                "skipped_unavailable_for_pilot": skipped_unavailable,
                "partial_pilot": allow_partial_pilot and bool(skipped_unavailable),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    project["render"]["ffconcat_path"] = str(ffconcat_path)
    project["render"]["slideshow_timeline_path"] = str(timeline_json_path)
    project["render"]["edit_decision_list_path"] = str(edit_decision_list_path)
    project["render"]["timeline_skipped_by_human_review"] = skipped_by_review
    project["render"]["timeline_skipped_unavailable_for_pilot"] = skipped_unavailable
    project["render"]["partial_pilot"] = allow_partial_pilot and bool(skipped_unavailable)
    project["render"]["status"] = "timeline_built"
    project["current_stage"] = "render"
    save_project(project_json, project)

    print(ffconcat_path)
    print(timeline_json_path)


if __name__ == "__main__":
    main()
