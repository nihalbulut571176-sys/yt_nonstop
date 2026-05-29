import argparse
import subprocess
import sys
from pathlib import Path

from project_pipeline_utils import append_event, append_log, load_json, load_project, mark_stage, save_json, save_project


ROOT = Path(__file__).resolve().parents[1]


def resolve_source_dir(source_dir: Path) -> Path:
    if list(source_dir.glob("*.png")):
        return source_dir
    nested_images_dir = source_dir / "images"
    if nested_images_dir.exists() and list(nested_images_dir.glob("*.png")):
        return nested_images_dir
    return source_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    source_dir = Path(project["images"]["raw_images_dir"])
    output_dir = Path(project["images"]["normalized_images_dir"])
    run_manifest_path = Path(project["images"]["run_manifest_path"])
    selected_manifest_path = Path(project["images"]["selected_images_manifest_path"])
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    scene_plan_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])

    if not source_dir.exists():
        raise FileNotFoundError(f"Raw images dir not found: {source_dir}")
    source_dir = resolve_source_dir(source_dir)
    if not run_manifest_path.exists():
        raise FileNotFoundError(f"Image manifest not found: {run_manifest_path}")
    if not scene_plan_path.exists():
        raise FileNotFoundError(f"Scene plan not found: {scene_plan_path}")

    append_log(project, f"Normalizing images from {source_dir} into {output_dir}")
    append_event(project, {"kind": "stage_start", "stage": "normalize_images"})
    mark_stage(project, "normalize_images", "running", current_stage="normalize_images")
    save_project(project_json, project)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "normalize_images_for_video.py"),
        "--source",
        str(source_dir),
        "--output",
        str(output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
    ]
    subprocess.run(cmd, check=True)

    project = load_project(project_json)
    manifest = load_json(run_manifest_path)
    scene_plan = load_json(scene_plan_path)
    selected_manifest = load_json(selected_manifest_path) if selected_manifest_path.exists() else {"selected_images": []}
    scene_map = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", [])}
    selected_by_scene = {
        row["scene_id"]: row
        for row in selected_manifest.get("selected_images", [])
        if row.get("scene_id")
    }

    for record in manifest.get("generated_images", []):
        output_file = record.get("output_file")
        if not output_file:
            continue
        normalized_path = str(output_dir / output_file)
        record["normalized_image_path"] = normalized_path
        if Path(normalized_path).exists():
            scene = scene_map.get(record["scene_id"])
            if scene:
                scene["still_image_path"] = normalized_path
                scene["render_asset_path"] = normalized_path
                scene["render_source"] = "still"
                notes = [note for note in scene.get("notes", []) if note != "Still image pending"]
                if "Normalized image ready" not in notes:
                    notes.append("Normalized image ready")
                scene["notes"] = notes
            selected_row = selected_by_scene.get(record["scene_id"])
            if selected_row and selected_row.get("selected_image_path") == record.get("image_path"):
                selected_row["normalized_image_path"] = normalized_path
                selected_row["selected_image_path"] = normalized_path

    if "normalization" not in manifest:
        manifest["normalization"] = {}
    manifest["normalization"]["target_width"] = args.width
    manifest["normalization"]["target_height"] = args.height
    manifest["normalization"]["output_dir"] = str(output_dir)
    save_json(run_manifest_path, manifest)
    save_json(scene_plan_path, scene_plan)
    if selected_manifest.get("selected_images"):
        save_json(selected_manifest_path, selected_manifest)

    project["images"]["status"] = "normalized"
    project["current_stage"] = "timeline"
    save_project(project_json, project)
    append_event(project, {"kind": "stage_end", "stage": "normalize_images", "status": "normalized"})
    append_log(project, "Image normalization completed")

    print(output_dir)


if __name__ == "__main__":
    main()
