import argparse
import json
from pathlib import Path


def safe_ffconcat_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", r"'\''")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    scenes = scene_plan.get("scenes", [])
    if not scenes:
        raise RuntimeError(f"No scenes found in {scene_plan_path}")

    renders_dir = Path(project["meta"]["project_root"]) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ffconcat_path = renders_dir / "timeline.ffconcat"
    timeline_json_path = renders_dir / "slideshow_timeline.json"

    ffconcat_lines = ["ffconcat version 1.0"]
    timeline = []

    for scene in scenes:
        image_path_str = scene.get("render_asset_path") or scene.get("still_image_path")
        if not image_path_str:
            raise FileNotFoundError(f"Scene {scene.get('scene_id')} has no still image path")
        image_path = Path(image_path_str)
        if not image_path.exists():
            raise FileNotFoundError(f"Missing image for scene {scene.get('scene_id')}: {image_path}")

        duration = float(scene["duration"])
        ffconcat_lines.append(f"file '{safe_ffconcat_path(image_path)}'")
        ffconcat_lines.append(f"duration {duration:.6f}")
        timeline.append(
            {
                "scene_id": scene["scene_id"],
                "shot_index": scene["shot_index"],
                "start": scene["start"],
                "end": scene["end"],
                "duration": duration,
                "image": str(image_path),
                "voice_text": scene.get("voice_text", ""),
            }
        )

    last_image = Path(scenes[-1].get("render_asset_path") or scenes[-1].get("still_image_path"))
    ffconcat_lines.append(f"file '{safe_ffconcat_path(last_image)}'")

    ffconcat_path.write_text("\n".join(ffconcat_lines) + "\n", encoding="utf-8")
    timeline_json_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    project["render"]["ffconcat_path"] = str(ffconcat_path)
    project["render"]["slideshow_timeline_path"] = str(timeline_json_path)
    project["render"]["status"] = "completed"
    project["current_stage"] = "generate_publishing_drafts"
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(ffconcat_path)
    print(timeline_json_path)


if __name__ == "__main__":
    main()
