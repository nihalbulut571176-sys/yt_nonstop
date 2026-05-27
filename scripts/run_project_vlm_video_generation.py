import argparse
import json
import subprocess
import sys
from pathlib import Path

from project_pipeline_utils import append_event, append_log, load_json, load_project, save_json, save_project


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")


def build_scene_lookup(package: dict, scene_plan: dict) -> tuple[dict[int, str], dict[str, dict]]:
    scene_by_prompt_index = {prompt_index: item["scene_id"] for prompt_index, item in enumerate(package.get("items", []), start=1)}
    scene_map = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", [])}
    return scene_by_prompt_index, scene_map


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--task-retries", type=int, default=1)
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=5)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    prompt_file = Path(project["prompts"]["generator_ready_path"])
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    workdir = Path(project["animation"]["run_manifest_path"]).parent
    workdir.mkdir(parents=True, exist_ok=True)

    if not prompt_file.exists():
        raise FileNotFoundError(f"Generator-ready prompt file not found: {prompt_file}")
    if not prompt_package_path.exists():
        raise FileNotFoundError(f"Prompt package not found: {prompt_package_path}")
    if not scene_plan_path.exists():
        raise FileNotFoundError(f"Scene plan not found: {scene_plan_path}")

    append_log(project, f"Starting VLM Unstop video generation in {workdir}")
    append_event(project, {"kind": "stage_start", "stage": "generate_videos"})
    project["animation"]["status"] = "running"
    project["current_stage"] = "generate_videos"
    save_project(project_json, project)

    scene_plan = load_json(scene_plan_path)
    durations = [float(scene.get("duration", 4.0) or 4.0) for scene in scene_plan.get("scenes", [])]
    durations_path = workdir / "scene_durations.json"
    save_json(durations_path, durations)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "veononstop_text_to_video.py"),
        "--prompts-file",
        str(prompt_file),
        "--durations-json",
        str(durations_path),
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
    if args.stop_on_error:
        cmd.append("--stop-on-error")
    subprocess.run(cmd, check=True)

    project = load_project(project_json)
    raw_manifest = load_json(Path(project["animation"]["run_manifest_path"]))
    run_summary_path = workdir / "run_summary.json"
    run_summary = load_json(run_summary_path) if run_summary_path.exists() else {"done": 0, "skipped": 0, "failed": 0}
    prompt_package = load_json(prompt_package_path)
    scene_plan = load_json(scene_plan_path)
    scene_by_prompt_index, scene_map = build_scene_lookup(prompt_package, scene_plan)

    generated_videos = []
    for record in raw_manifest:
        prompt_index = int(record["source_prompt_index"])
        scene_id = scene_by_prompt_index.get(prompt_index)
        if not scene_id:
            continue
        video_path = record["output"]
        status = "success" if Path(video_path).exists() else "missing"
        generated_videos.append(
            {
                "scene_id": scene_id,
                "source_prompt_index": prompt_index,
                "prompt": record.get("prompt", ""),
                "requested_duration": record.get("requested_duration"),
                "duration_seconds": record.get("duration_seconds"),
                "video_path": video_path,
                "status": status,
            }
        )
        scene = scene_map.get(scene_id)
        if scene and status == "success":
            scene["video_path"] = video_path
            scene["render_source"] = "video"
            scene["render_asset_path"] = video_path
            scene["animation_status"] = "generated"
            notes = [note for note in scene.get("notes", []) if note != "Still image pending"]
            if "Generated video ready" not in notes:
                notes.append("Generated video ready")
            scene["notes"] = notes

    enriched_manifest = {
        "project_id": project["project_id"],
        "profile_id": project["profile_id"],
        "prompt_file": str(prompt_file),
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
    append_log(project, f"VLM Unstop generation completed: {enriched_manifest['completed_count']} videos ready")

    print(project["animation"]["run_manifest_path"])


if __name__ == "__main__":
    main()
