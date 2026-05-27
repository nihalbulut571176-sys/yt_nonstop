import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
VEO_RUNNER = ROOT / "scripts" / "veononstop_image_to_video.py"
TARGETS_BUILDER = ROOT / "scripts" / "build_project_animation_targets.py"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--policy", default="first_minute_then_every_third")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--task-retries", type=int, default=1)
    parser.add_argument("--retry-delay-seconds", type=float, default=20.0)
    parser.add_argument("--cookie-retry-delay-seconds", type=float, default=30.0)
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=5)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--duration", default="")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--check-account", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_json(project_json)
    project_root = Path(project["meta"]["project_root"])
    animation_dir = project_root / "animation"
    workdir = animation_dir / "veononstop_run"
    workdir.mkdir(parents=True, exist_ok=True)

    run(
        [
            sys.executable,
            str(TARGETS_BUILDER),
            "--project-json",
            str(project_json),
            "--policy",
            args.policy,
            "--videos-dir",
            str(workdir / "videos"),
        ]
    )

    project = load_json(project_json)
    timeline_subset_path = Path(project["animation"]["timeline_subset_path"])
    if not timeline_subset_path.exists():
        raise FileNotFoundError(f"Animation target timeline not found: {timeline_subset_path}")

    cmd = [
        sys.executable,
        str(VEO_RUNNER),
        "--timeline",
        str(timeline_subset_path),
        "--workdir",
        str(workdir),
        "--concurrency",
        str(args.concurrency),
        "--task-retries",
        str(args.task_retries),
        "--retry-delay-seconds",
        str(args.retry_delay_seconds),
        "--cookie-retry-delay-seconds",
        str(args.cookie_retry_delay_seconds),
        "--stop-after-consecutive-failures",
        str(args.stop_after_consecutive_failures),
        "--poll-seconds",
        str(args.poll_seconds),
        "--max-polls",
        str(args.max_polls),
        "--count",
        str(args.count),
    ]
    if args.duration:
        cmd.extend(["--duration", args.duration])
    if args.check_account:
        cmd.append("--check-account")
    run(cmd)

    run(
        [
            sys.executable,
            str(TARGETS_BUILDER),
            "--project-json",
            str(project_json),
            "--policy",
            args.policy,
            "--videos-dir",
            str(workdir / "videos"),
        ]
    )

    project = load_json(project_json)
    run_summary_path = workdir / "run_summary.json"
    run_summary = load_json(run_summary_path) if run_summary_path.exists() else {}
    failed_count = int(run_summary.get("failed", 0) or 0)

    project["animation"]["status"] = "completed" if failed_count == 0 else "partial"
    project["animation"]["provider"] = "veononstop"
    project["animation"]["policy_name"] = args.policy
    project["animation"]["run_manifest_path"] = str(workdir / "run_manifest.json")
    project["animation"]["videos_dir"] = str(workdir / "videos")
    project["animation"]["success_log_path"] = str(workdir / "success.jsonl")
    project["animation"]["failed_log_path"] = str(workdir / "failed.jsonl")
    project["animation"]["run_summary_path"] = str(run_summary_path)
    project["render"]["render_strategy"] = "mixed_cut"
    project["current_stage"] = "mixed_render"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(workdir)
    print(json.dumps(run_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
