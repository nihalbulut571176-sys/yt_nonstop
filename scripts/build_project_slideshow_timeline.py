import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project


def safe_ffconcat_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", r"'\''")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    montage_map_path = Path(project["exports"]["montage_timing_map_json_path"])
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    scene_plan_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    scenes = scene_plan.get("scenes", [])
    if not scenes:
        raise RuntimeError(f"No scenes found in {scene_plan_path}")
    montage_rows = json.loads(montage_map_path.read_text(encoding="utf-8")) if montage_map_path.exists() else []
    montage_by_frame = {row["frame_id"]: row for row in montage_rows if row.get("frame_id")}
    selected_manifest_path = Path(project["images"].get("selected_images_manifest_path", ""))
    selected_manifest = json.loads(selected_manifest_path.read_text(encoding="utf-8")) if selected_manifest_path.exists() else {}
    selected_by_scene = {
        row["scene_id"]: row
        for row in selected_manifest.get("selected_images", [])
        if row.get("scene_id")
    }

    renders_dir = Path(project["meta"]["project_root"]) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ffconcat_path = renders_dir / "timeline.ffconcat"
    timeline_json_path = renders_dir / "slideshow_timeline.json"
    edit_decision_list_path = Path(project["render"]["edit_decision_list_path"])
    audio_duration = float(project["inputs"].get("audio_duration_seconds") or 0)
    if audio_duration <= 0:
        audio_duration = float(scenes[-1]["end"])

    ffconcat_lines = ["ffconcat version 1.0"]
    timeline = []
    edit_decision_list = []

    for index, scene in enumerate(scenes):
        montage_row = montage_by_frame.get(scene.get("frame_id", ""))
        selected_row = selected_by_scene.get(scene["scene_id"], {})
        image_path_str = (
            selected_row.get("selected_image_path")
            or selected_row.get("image_path")
            or (montage_row or {}).get("asset_image_path")
            or scene.get("render_asset_path")
            or scene.get("still_image_path")
        )
        if not image_path_str:
            raise FileNotFoundError(f"Scene {scene.get('scene_id')} has no still image path")
        image_path = Path(image_path_str)
        if not image_path.exists():
            raise FileNotFoundError(f"Missing image for scene {scene.get('scene_id')}: {image_path}")

        start = float(scene["start"])
        speech_end = float(scene["end"])
        next_start = float(scenes[index + 1]["start"]) if index + 1 < len(scenes) else audio_duration
        display_end = max(next_start, speech_end)
        if index + 1 == len(scenes):
            display_end = max(audio_duration, speech_end)
        duration = max(0.001, display_end - start)
        ffconcat_lines.append(f"file '{safe_ffconcat_path(image_path)}'")
        ffconcat_lines.append(f"duration {duration:.6f}")
        timeline.append(
            {
                "frame_id": scene.get("frame_id", ""),
                "beat_id": scene.get("beat_id", ""),
                "scene_id": scene["scene_id"],
                "shot_index": scene["shot_index"],
                "start": start,
                "end": display_end,
                "duration": duration,
                "speech_end": speech_end,
                "image": str(image_path),
                "voice_text": scene.get("voice_text", ""),
                "srt_indices": (montage_row or {}).get("srt_indices", scene.get("srt_indices", "")),
                "screen_action": (montage_row or {}).get("screen_action", ""),
                "motion_id": scene.get("motion_id", ""),
                "motion_plan": scene.get("motion_plan", {}),
            }
        )
        edit_decision_list.append(
            {
                "frame_id": scene.get("frame_id", ""),
                "beat_id": scene.get("beat_id", ""),
                "scene_id": scene["scene_id"],
                "image_path": str(image_path),
                "start": start,
                "end": display_end,
                "duration": duration,
                "motion": scene.get("motion_id") or scene.get("motion_plan", {}).get("motion") or "slow_push_in",
                "transition_in": scene.get("transition_in", "cut"),
                "transition_out": scene.get("transition_out", "cut_on_phrase_end"),
                "voice_text": scene.get("voice_text", ""),
                "visualized_claim": scene.get("visualized_claim", ""),
                "sync_rule": "frame starts exactly at beat start",
            }
        )

    last_image = Path(scenes[-1].get("render_asset_path") or scenes[-1].get("still_image_path"))
    ffconcat_lines.append(f"file '{safe_ffconcat_path(last_image)}'")

    ffconcat_path.write_text("\n".join(ffconcat_lines) + "\n", encoding="utf-8")
    timeline_json_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    edit_decision_list_path.write_text(json.dumps({"project_id": project["project_id"], "edl": edit_decision_list}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    project["render"]["ffconcat_path"] = str(ffconcat_path)
    project["render"]["slideshow_timeline_path"] = str(timeline_json_path)
    project["render"]["edit_decision_list_path"] = str(edit_decision_list_path)
    project["render"]["status"] = "timeline_built"
    project["current_stage"] = "render"
    save_project(project_json, project)

    print(ffconcat_path)
    print(timeline_json_path)


if __name__ == "__main__":
    main()
