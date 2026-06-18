from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.pipeline.project_config import load_project, save_project  # noqa: E402


BASE_TEMPLATE_PATH = ROOT / "deliverables" / "project.template.json"
PROFILE_TEMPLATE_PATH = ROOT / "sample_projects" / "real_pilot_90s" / "project.template.json"

SUPPORTED_PROFILES = {"no_vlm_production"}
PROJECT_DIRS = [
    "input",
    "transcript",
    "scene_plan",
    "planning",
    "prompts",
    "exports",
    "reports",
    "qc",
    "logs",
    "renders",
    "config",
    "images/run",
    "images/normalized",
    "assets/references",
    "assets/references/characters",
    "publishing/thumbnails/candidates",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = {key: deep_merge(base.get(key), value) if key in base else value for key, value in overlay.items()}
        for key, value in base.items():
            merged.setdefault(key, value)
        return merged
    return overlay


def ensure_project_dirs(project_root: Path) -> None:
    for relative_dir in PROJECT_DIRS:
        (project_root / relative_dir).mkdir(parents=True, exist_ok=True)


def copy_input_file(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def stage_audio(source_audio: Path, project_root: Path) -> Path:
    suffix = source_audio.suffix.lower() or ".bin"
    return copy_input_file(source_audio, project_root / "input" / f"source_audio{suffix}")


def bootstrap_project(
    *,
    project_root: Path,
    source_srt: Path | None,
    source_audio: Path | None,
    raw_text: Path | None = None,
    setup_notes: Path | None = None,
    profile: str,
) -> Path:
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"Unsupported profile `{profile}`")

    ensure_project_dirs(project_root)

    if not source_srt and not source_audio:
        raise ValueError("Either source_srt or source_audio is required")

    audio_path = stage_audio(source_audio, project_root) if source_audio else None
    audio_stem = audio_path.stem if audio_path else "raw_whisper"
    raw_whisper_path = project_root / "transcript" / f"{audio_stem}.srt"
    raw_segments_path = project_root / "transcript" / f"{audio_stem}.segments.json"
    raw_meta_path = project_root / "transcript" / f"{audio_stem}.meta.json"
    cleaned_srt_path = project_root / "transcript" / "cleaned.srt"

    if source_srt:
        input_srt_path = copy_input_file(source_srt, project_root / "input" / "source.srt")
        raw_whisper_path = copy_input_file(source_srt, project_root / "transcript" / "raw_whisper.srt")
        cleaned_srt_path = copy_input_file(source_srt, cleaned_srt_path)

    project = deep_merge(load_json(BASE_TEMPLATE_PATH), load_json(PROFILE_TEMPLATE_PATH))
    now = iso_now()
    project_id = project_root.name
    has_srt = source_srt is not None
    project["profile_id"] = profile
    project["project_id"] = project_id
    project["created_at"] = now
    project["updated_at"] = now
    project["status"] = "draft"
    project["current_stage"] = "ingest_srt" if has_srt else "transcription"
    project.setdefault("meta", {})
    project["meta"]["project_root"] = str(project_root.resolve())
    project["meta"]["title"] = project_id.replace("_", " ")
    project["meta"]["language"] = str(project["meta"].get("language") or "auto")

    project.setdefault("inputs", {})
    project["inputs"]["audio_path"] = str(audio_path) if audio_path else None
    project["inputs"]["audio_duration_seconds"] = None
    project["inputs"]["raw_text_path"] = str(project_root / "input" / "raw_text.md")
    project["inputs"]["raw_text_char_count"] = 0

    project.setdefault("rewrite", {})
    project["rewrite"]["status"] = "pending"
    project["rewrite"]["source_text_path"] = str(project_root / "input" / "raw_text.md")
    project["rewrite"]["rewritten_script_path"] = str(project_root / "input" / "voice_script.md")
    project["rewrite"]["approved_script_path"] = str(project_root / "input" / "voice_script_approved.md")

    project.setdefault("transcription", {})
    project["transcription"]["status"] = "completed" if has_srt else "pending"
    if not has_srt:
        project["transcription"]["model"] = "base"
    project["transcription"]["audio_path"] = str(audio_path) if audio_path else None
    project["transcription"]["raw_srt_path"] = str(raw_whisper_path)
    project["transcription"]["srt_path"] = str(raw_whisper_path)
    project["transcription"]["segments_json_path"] = None if has_srt else str(raw_segments_path)
    project["transcription"]["meta_json_path"] = None if has_srt else str(raw_meta_path)

    project.setdefault("transcript_cleanup", {})
    project["transcript_cleanup"]["status"] = "completed" if has_srt else "pending"
    project["transcript_cleanup"]["source_text_path"] = str(project_root / "input" / "raw_text.md")
    project["transcript_cleanup"]["used_source_path"] = None
    project["transcript_cleanup"]["cleaned_srt_path"] = str(cleaned_srt_path)
    project["transcript_cleanup"]["cleaned_segments_json_path"] = str(project_root / "transcript" / "cleaned_segments.json")
    project["transcript_cleanup"]["cleaned_timed_transcript_md_path"] = str(project_root / "transcript" / "cleaned_timed_transcript.md")
    project["transcript_cleanup"]["cleanup_report_path"] = str(project_root / "transcript" / "cleanup_report.json")

    project.setdefault("scene_plan", {})
    project["scene_plan"]["status"] = "pending"
    project["scene_plan"]["source_srt_path"] = str(cleaned_srt_path)
    project["scene_plan"]["scene_plan_path"] = str(project_root / "scene_plan" / "scene_plan.json")
    project["scene_plan"]["long_segment_report_path"] = str(project_root / "scene_plan" / "long_segment_report.json")
    project["scene_plan"]["scene_count"] = 0
    project["scene_plan"]["original_segment_count"] = 0

    project.setdefault("planning", {})
    project["planning"]["visual_allocation_provider"] = "disabled"
    project["planning"]["narration_beats_llm"] = {"mode": "disabled"}
    project["planning"]["visual_allocation_llm"] = {"mode": "disabled"}

    project.setdefault("prompts", {})
    project["prompts"]["prompt_authoring_llm"] = {"mode": "disabled"}
    project["prompts"]["prompt_repair_llm"] = {"mode": "disabled"}

    project.setdefault("providers", {})
    project["providers"]["llm_provider"] = {"mode": "disabled"}

    project.setdefault("generation", {})
    project["generation"]["provider_mode"] = "disabled"
    project["generation"]["image_generation_mode"] = "disabled"
    project["generation"]["key_beat_variants"] = int(project["generation"].get("key_beat_variants", 1) or 1)
    project["generation"]["normal_beat_variants"] = int(project["generation"].get("normal_beat_variants", 1) or 1)
    project["generation"]["allow_regeneration"] = bool(project["generation"].get("allow_regeneration", True))
    project["generation"]["max_regeneration_attempts"] = int(project["generation"].get("max_regeneration_attempts", 2) or 2)

    project.setdefault("workflow", {})
    project["workflow"]["profile"] = profile
    project["workflow"]["render_dry_run"] = bool(has_srt)
    project["workflow"]["image_generation_enabled"] = not has_srt

    project.setdefault("images", {})
    project["images"]["status"] = "pending"
    project["images"]["provider"] = "disabled"
    project["images"]["route"] = "disabled"
    project["images"]["generated_count"] = 0
    project["images"]["failed_count"] = 0

    project.setdefault("animation", {})
    project["animation"]["status"] = "skipped"
    project["animation"]["policy_name"] = "disabled"
    project["animation"]["provider"] = "disabled"

    project.setdefault("render", {})
    project["render"]["status"] = "pending"
    project["render"]["render_strategy"] = "images_only"
    project["render"]["render_mode"] = "dry_run" if has_srt else "full"

    project.setdefault("qc", {})
    project["qc"]["image_semantic_qc_mode"] = "disabled"
    project["qc"]["allow_manual_review_without_vlm"] = True
    project["qc"]["prompt_repair_llm"] = {"mode": "disabled"}

    project.setdefault("notes", [])
    project["notes"] = [
        "Bootstrapped by scripts/bootstrap_real_pilot_project.py",
        "Default profile disables real LLM, VLM, and image generation providers.",
        "Audio/text intake can run external image generation only when CLI --real-generation and provider env are configured.",
    ]

    project_json = project_root / "project.json"
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Normalize all default paths against the actual project root and stamp updated_at.
    normalized_project = load_project(project_json)
    save_project(project_json, normalized_project)

    if raw_text:
        copy_input_file(raw_text, project_root / "input" / "raw_text.md")
    else:
        (project_root / "input" / "raw_text.md").write_text("", encoding="utf-8")
    if setup_notes:
        copy_input_file(setup_notes, project_root / "input" / "project_setup_notes.md")
    (project_root / "input" / "voice_script.md").write_text("", encoding="utf-8")
    (project_root / "input" / "voice_script_approved.md").write_text("", encoding="utf-8")
    return project_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap a real 60-90 second pilot project from an existing SRT/audio pair.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source-srt")
    parser.add_argument("--source-audio")
    parser.add_argument("--raw-text")
    parser.add_argument("--setup-notes")
    parser.add_argument("--profile", default="no_vlm_production", choices=sorted(SUPPORTED_PROFILES))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).expanduser().resolve()
    source_srt = Path(args.source_srt).expanduser().resolve() if args.source_srt else None
    source_audio = Path(args.source_audio).expanduser().resolve() if args.source_audio else None
    raw_text = Path(args.raw_text).expanduser().resolve() if args.raw_text else None
    setup_notes = Path(args.setup_notes).expanduser().resolve() if args.setup_notes else None

    if source_srt and not source_srt.exists():
        raise FileNotFoundError(f"Source SRT not found: {source_srt}")
    if source_audio and not source_audio.exists():
        raise FileNotFoundError(f"Source audio not found: {source_audio}")
    if not source_srt and not source_audio:
        raise ValueError("Either --source-srt or --source-audio is required")
    if raw_text and not raw_text.exists():
        raise FileNotFoundError(f"Raw text not found: {raw_text}")
    if setup_notes and not setup_notes.exists():
        raise FileNotFoundError(f"Setup notes not found: {setup_notes}")

    project_json = bootstrap_project(
        project_root=project_root,
        source_srt=source_srt,
        source_audio=source_audio,
        raw_text=raw_text,
        setup_notes=setup_notes,
        profile=args.profile,
    )

    run_cmd = f'yt-nonstop run --project-json "{project_json}" --to production_report'
    status_cmd = f'yt-nonstop status --project-json "{project_json}"'

    print(project_json)
    print("")
    print("Next commands:")
    print(run_cmd)
    print(status_cmd)
    print("")
    print("Enable real providers later:")
    print("1. Configure an LLM provider under project.providers.llm_provider or stage-specific *_llm blocks.")
    print("2. Switch planning.visual_allocation_provider from disabled to file or external if you want provider-authored allocation.")
    print("3. Change qc.image_semantic_qc_mode from disabled to heuristic or external when VLM checks are ready.")
    print("4. Set images.provider and generation.image_generation_mode to a real generation backend before running image stages.")
    print("5. Turn workflow.render_dry_run to false only when ffmpeg inputs and provider outputs are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
