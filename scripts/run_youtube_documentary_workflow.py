import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
DEFAULT_PROJECTS_DIR = ROOT / "projects"


def load_dotenv(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for raw_line in dotenv_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_markdown(path: Path, lines: list[str]) -> None:
    ensure_dir(path.parent)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def render_input_report(
    report_path: Path,
    *,
    project_id: str,
    project_root: Path,
    audio_path: Path | None,
    raw_text_path: Path | None,
    dotenv_path: Path,
    env_loaded: bool,
    fastgen_key_present: bool,
    ffmpeg_ok: bool,
    ffprobe_ok: bool,
    missing: list[str],
    warnings: list[str],
) -> None:
    lines = [
        "# Input Check Report",
        "",
        f"- Project ID: `{project_id}`",
        f"- Project root: `{project_root}`",
        f"- Audio input: `{audio_path}`" if audio_path else "- Audio input: missing",
        f"- Raw transcript input: `{raw_text_path}`" if raw_text_path else "- Raw transcript input: not provided",
        f"- `.env` present: `{dotenv_path.exists()}`",
        f"- Environment loaded: `{env_loaded}`",
        f"- `FAST_GEN_API_KEY` present: `{fastgen_key_present}`",
        f"- `ffmpeg` available: `{ffmpeg_ok}`",
        f"- `ffprobe` available: `{ffprobe_ok}`",
        "",
        "## Missing Inputs",
    ]
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings"])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- None")
    write_markdown(report_path, lines)


def render_missing_inputs_report(report_path: Path, missing: list[str], project_root: Path) -> None:
    lines = [
        "# Missing Inputs Report",
        "",
        "The workflow could not start because required inputs or runtime dependencies are missing.",
        "",
        f"- Expected project root: `{project_root}`",
        "",
        "## Missing",
    ]
    lines.extend(f"- {item}" for item in missing)
    lines.extend(
        [
            "",
            "## Required minimum inputs",
            "",
            "- `input/transcript.txt` or pass `--raw-text-path`",
            "- `input/voiceover.mp3` or pass `--audio-source`",
            "- `.env` with `FAST_GEN_API_KEY`",
            "- `ffmpeg` and `ffprobe` on PATH",
        ]
    )
    write_markdown(report_path, lines)


def run_command(cmd: list[str], dry_run: bool) -> str:
    if dry_run:
        print("DRY-RUN:", " ".join(cmd))
        return ""
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def resolve_default_raw_text(project_root: Path) -> Path | None:
    candidates = [
        project_root / "input" / "transcript.txt",
        project_root / "input" / "transcript.md",
        project_root / "input" / "raw_text.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end YouTube documentary still-image workflow: audio + transcript -> planned prompts -> FastGen images -> rendered video."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--audio-source", help="Local path or URL for the voiceover audio.")
    parser.add_argument("--raw-text-path", help="Local path to the narration transcript.")
    parser.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    parser.add_argument("--from-stage")
    parser.add_argument("--to-stage", default="render")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--skip-transcribe", action="store_true")
    parser.add_argument(
        "--auto-author-llm",
        dest="auto_author_llm",
        action="store_true",
        help="Use the internal Codex/LLM stage to author FastGen prompt drafts.",
    )
    parser.add_argument(
        "--no-auto-author-llm",
        dest="auto_author_llm",
        action="store_false",
        help="Skip internal LLM prompt authoring and expect drafts to exist already.",
    )
    parser.add_argument("--require-filled-prompts", action="store_true")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--image-size", default="1792x1024")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--image-retry-rounds", type=int, default=3)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--soften-policy-prompts", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(auto_author_llm=True)
    args = parser.parse_args()

    projects_dir = Path(args.projects_dir).resolve()
    project_root = projects_dir / args.project_id
    logs_dir = ensure_dir(project_root / "logs")
    input_report_path = logs_dir / "input_check_report.md"
    missing_report_path = logs_dir / "missing_inputs_report.md"

    audio_path = Path(args.audio_source).expanduser().resolve() if args.audio_source and not args.audio_source.startswith(("http://", "https://")) else None
    raw_text_path = Path(args.raw_text_path).expanduser().resolve() if args.raw_text_path else resolve_default_raw_text(project_root)

    dotenv_path = ROOT / ".env"
    dotenv_values = load_dotenv(dotenv_path)
    env_loaded = bool(dotenv_values)
    for key, value in dotenv_values.items():
        os.environ.setdefault(key, value)

    ffmpeg_ok = tool_available("ffmpeg")
    ffprobe_ok = tool_available("ffprobe")
    fastgen_key_present = bool(os.environ.get("FAST_GEN_API_KEY", "").strip())

    missing: list[str] = []
    warnings: list[str] = []

    if args.audio_source:
        if audio_path and not audio_path.exists():
            missing.append(f"Audio source not found: {audio_path}")
    elif not args.resume:
        missing.append("Audio source is required for a new run. Pass `--audio-source`.")

    if raw_text_path is None or not raw_text_path.exists():
        warnings.append("Raw transcript file was not provided. The workflow can continue with Whisper timing only, but prompt quality may drop.")

    if not dotenv_path.exists():
        missing.append(f"Missing `.env` at {dotenv_path}")
    elif not fastgen_key_present and args.to_stage in {"generate_images", "normalize_images", "timeline", "render"}:
        missing.append("`FAST_GEN_API_KEY` is empty in `.env`.")

    if not ffmpeg_ok:
        missing.append("`ffmpeg` is not available on PATH.")
    if not ffprobe_ok:
        missing.append("`ffprobe` is not available on PATH.")

    render_input_report(
        input_report_path,
        project_id=args.project_id,
        project_root=project_root,
        audio_path=audio_path if audio_path else (Path(args.audio_source) if args.audio_source else None),
        raw_text_path=raw_text_path,
        dotenv_path=dotenv_path,
        env_loaded=env_loaded,
        fastgen_key_present=fastgen_key_present,
        ffmpeg_ok=ffmpeg_ok,
        ffprobe_ok=ffprobe_ok,
        missing=missing,
        warnings=warnings,
    )

    if missing:
        render_missing_inputs_report(missing_report_path, missing, project_root)
        raise SystemExit(1)

    if args.preflight_only:
        print(input_report_path)
        return

    project_json = project_root / "project.json"
    if not project_json.exists():
        bootstrap_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "bootstrap_fastgen_only_project.py"),
            "--project-id",
            args.project_id,
            "--audio-source",
            args.audio_source,
            "--projects-dir",
            str(projects_dir),
            "--whisper-model",
            args.whisper_model,
            "--language",
            args.language,
            "--compute-type",
            args.compute_type,
            "--device",
            args.device,
        ]
        if raw_text_path:
            bootstrap_cmd.extend(["--raw-text-path", str(raw_text_path)])
        if args.skip_transcribe:
            bootstrap_cmd.append("--skip-transcribe")
        bootstrap_stdout = run_command(bootstrap_cmd, args.dry_run)
        if bootstrap_stdout:
            project_json = Path(bootstrap_stdout.splitlines()[-1].strip())

    runner_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_fastgen_only_project.py"),
        "--project-json",
        str(project_json),
        "--to",
        args.to_stage,
        "--image-size",
        args.image_size,
        "--concurrency",
        str(args.concurrency),
        "--poll-seconds",
        str(args.poll_seconds),
        "--max-polls",
        str(args.max_polls),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--image-retry-rounds",
        str(args.image_retry_rounds),
    ]
    if args.from_stage:
        runner_cmd.extend(["--from", args.from_stage])
    if args.resume:
        runner_cmd.append("--resume")
    if args.auto_author_llm:
        runner_cmd.append("--auto-author-llm")
    if args.require_filled_prompts:
        runner_cmd.append("--require-filled-prompts")
    if args.soften_policy_prompts:
        runner_cmd.append("--soften-policy-prompts")
    if args.dry_run:
        runner_cmd.append("--dry-run")

    run_command(runner_cmd, args.dry_run)
    print(project_json)


if __name__ == "__main__":
    main()
