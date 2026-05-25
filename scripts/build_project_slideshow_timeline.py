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
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    scene_plan_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    scenes = scene_plan.get("scenes", [])
    if not scenes:
        raise RuntimeError(f"No scenes found in {scene_plan_path}")

    renders_dir = Path(project["meta"]["project_root"]) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ffconcat_path = renders_dir / "timeline.ffconcat"
    timeline_json_path = renders_dir / "slideshow_timeline.json"
    audio_duration = float(project["inputs"].get("audio_duration_seconds") or 0)
    if audio_duration <= 0:
        audio_duration = float(scenes[-1]["end"])

    ffconcat_lines = ["ffconcat version 1.0"]
    timeline = []

    for index, scene in enumerate(scenes):
        image_path_str = scene.get("render_asset_path") or scene.get("still_image_path")
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
                "scene_id": scene["scene_id"],
                "shot_index": scene["shot_index"],
                "start": start,
                "end": display_end,
                "duration": duration,
                "speech_end": speech_end,
                "image": str(image_path),
                "voice_text": scene.get("voice_text", ""),
                "motion_id": scene.get("motion_id", ""),
                "motion_plan": scene.get("motion_plan", {}),
            }
        )

    last_image = Path(scenes[-1].get("render_asset_path") or scenes[-1].get("still_image_path"))
    ffconcat_lines.append(f"file '{safe_ffconcat_path(last_image)}'")

    ffconcat_path.write_text("\n".join(ffconcat_lines) + "\n", encoding="utf-8")
    timeline_json_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    project["render"]["ffconcat_path"] = str(ffconcat_path)
    project["render"]["slideshow_timeline_path"] = str(timeline_json_path)
    project["render"]["status"] = "timeline_built"
    project["current_stage"] = "render"
    save_project(project_json, project)

    print(ffconcat_path)
    print(timeline_json_path)


if __name__ == "__main__":
    main()
