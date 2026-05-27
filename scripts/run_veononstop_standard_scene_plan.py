import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")


def load_scene_plan(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("scene plan json must be a JSON object")
    if not isinstance(data.get("items"), list):
        raise ValueError("scene plan json must contain an `items` array")
    return data


def normalize_requested_duration(value) -> str:
    if value in (4, "4", "4s"):
        return "4s"
    if value in (6, "6", "6s"):
        return "6s"
    if value in (8, "8", "8s", None, ""):
        return ""
    raise ValueError(f"Unsupported VEO duration preset: {value!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-plan-json", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--task-retries", type=int, default=1)
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=5)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    scene_plan_path = Path(args.scene_plan_json).resolve()
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    videos_dir = workdir / "videos"
    meta_dir = workdir / "meta"
    videos_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    scene_plan = load_scene_plan(scene_plan_path)
    items = scene_plan["items"]

    prompts = [str(item.get("prompt", "")).strip() for item in items]
    durations = [float(item.get("duration", 4.0) or 4.0) for item in items]
    requested_durations = [normalize_requested_duration(item.get("veo_duration_preset")) for item in items]

    prompts_file = workdir / "generator_ready_prompts.txt"
    durations_file = workdir / "scene_durations.json"
    requested_durations_file = workdir / "requested_durations.json"
    scene_manifest_file = workdir / "scene_manifest.json"

    prompts_file.write_text("\n\n".join(prompts).strip() + "\n", encoding="utf-8")
    durations_file.write_text(json.dumps(durations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    requested_durations_file.write_text(json.dumps(requested_durations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    scene_manifest = []
    for index, item in enumerate(items, start=1):
        scene_manifest.append(
            {
                "source_prompt_index": index,
                "scene_id": item.get("scene_id"),
                "start": item.get("start"),
                "end": item.get("end"),
                "duration": item.get("duration"),
                "start_timecode": item.get("start_timecode"),
                "end_timecode": item.get("end_timecode"),
                "veo_duration_preset": item.get("veo_duration_preset"),
                "shot_role": item.get("shot_role"),
                "visual_goal": item.get("visual_goal"),
                "brand_context": item.get("brand_context", []),
            }
        )
    scene_manifest_file.write_text(json.dumps(scene_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "veononstop_text_to_video.py"),
        "--prompts-file",
        str(prompts_file),
        "--durations-json",
        str(durations_file),
        "--requested-durations-json",
        str(requested_durations_file),
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


if __name__ == "__main__":
    main()
