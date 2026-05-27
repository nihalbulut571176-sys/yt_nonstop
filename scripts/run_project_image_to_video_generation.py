import argparse
import subprocess
import sys
from pathlib import Path

from project_pipeline_utils import append_event, append_log, load_json, load_project, save_json, save_project


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")


def build_timeline(scene_plan: dict) -> list[dict]:
    timeline = []
    for scene in scene_plan.get("scenes", []):
        image_path = scene.get("still_image_path") or scene.get("render_asset_path")
        if not image_path:
            raise FileNotFoundError(f"Scene {scene.get('scene_id')} has no normalized still image path")
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"Missing normalized still image for {scene.get('scene_id')}: {image_file}")

        timeline.append(
            {
                "shot_index": int(scene["shot_index"]),
                "scene_id": scene["scene_id"],
                "start": float(scene["start"]),
                "end": float(scene["end"]),
                "duration": float(scene["duration"]),
                "generated_index": int(scene.get("generated_index", scene["shot_index"])),
                "image": str(image_file),
                "source_kind": scene.get("source_kind", "original"),
                "prompt": str(scene.get("prompt", "")).strip(),
            }
        )
    return timeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--duration", default="")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--task-retries", type=int, default=1)
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=5)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    if not scene_plan_path.exists():
        raise FileNotFoundError(f"Scene plan not found: {scene_plan_path}")

    workdir = Path(project["animation"]["run_manifest_path"]).parent
    workdir.mkdir(parents=True, exist_ok=True)
    timeline_path = workdir / "scene_timeline.json"

    scene_plan = load_json(scene_plan_path)
    timeline = build_timeline(scene_plan)
    save_json(timeline_path, timeline)

    append_log(project, f"Starting Veo Nonstop image-to-video generation in {workdir}")
    append_event(project, {"kind": "stage_start", "stage": "generate_videos"})
    project["animation"]["status"] = "running"
    project["current_stage"] = "generate_videos"
    project["animation"]["timeline_subset_path"] = str(timeline_path)
    save_project(project_json, project)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "veononstop_image_to_video.py"),
        "--timeline",
        str(timeline_path),
        "--workdir",
        str(workdir),
        "--aspect-ratio",
        args.aspect_ratio,
        "--start",
        str(args.start),
        "--poll-seconds",
        str(args.poll_seconds),
        "--max-polls",
        str(args.max_polls),
        "--concurrency",
        str(args.concurrency),
        "--task-retries",
        str(args.task_retries),
        "--stop-after-consecutive-failures",
        str(args.stop_after_consecutive_failures),
    ]
    if args.end > 0:
        cmd.extend(["--end", str(args.end)])
    if args.duration:
        cmd.extend(["--duration", args.duration])
    if args.count != 1:
        cmd.extend(["--count", str(args.count)])
    if args.stop_on_error:
        cmd.append("--stop-on-error")

    subprocess.run(cmd, check=True)

    project = load_project(project_json)
    raw_manifest = load_json(Path(project["animation"]["run_manifest_path"]))
    run_summary_path = workdir / "run_summary.json"
    run_summary = load_json(run_summary_path) if run_summary_path.exists() else {"done": 0, "skipped": 0, "failed": 0}
    scene_plan = load_json(scene_plan_path)
    scene_map = {scene["shot_index"]: scene for scene in scene_plan.get("scenes", [])}

    generated_videos = []
    for record in raw_manifest:
        shot_index = int(record["shot_index"])
        scene = scene_map.get(shot_index)
        if not scene:
            continue
        video_path = record["output"]
        status = "success" if Path(video_path).exists() else "missing"
        generated_videos.append(
            {
                "scene_id": scene["scene_id"],
                "shot_index": shot_index,
                "image_path": record.get("image"),
                "prompt": record.get("source_prompt", record.get("prompt", "")),
                "video_path": video_path,
                "status": status,
            }
        )
        if status == "success":
            scene["video_path"] = video_path
            scene["render_source"] = "video"
            scene["render_asset_path"] = video_path
            scene["animation_status"] = "generated"
            notes = [note for note in scene.get("notes", []) if note not in {"Still image pending", "Normalized image ready"}]
            if "Generated video ready" not in notes:
                notes.append("Generated video ready")
            scene["notes"] = notes

    enriched_manifest = {
        "project_id": project["project_id"],
        "profile_id": project["profile_id"],
        "timeline_file": str(timeline_path),
        "workdir": str(workdir),
        "generated_videos": generated_videos,
        "failed_count": int(run_summary.get("failed", 0) or 0),
        "completed_count": sum(1 for item in generated_videos if item["status"] == "success"),
        "skipped_count": int(run_summary.get("skipped", 0) or 0),
    }
    save_json(Path(project["animation"]["run_manifest_path"]), enriched_manifest)
    save_json(scene_plan_path, scene_plan)

    project["animation"]["status"] = "generated"
    project["current_stage"] = "timeline"
    save_project(project_json, project)
    append_event(project, {"kind": "stage_end", "stage": "generate_videos", "status": "generated"})
    append_log(project, f"Image-to-video generation completed: {enriched_manifest['completed_count']} videos ready")

    print(project["animation"]["run_manifest_path"])


if __name__ == "__main__":
    main()
