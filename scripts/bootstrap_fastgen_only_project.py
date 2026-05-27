import argparse
import json
import mimetypes
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
TEMPLATE_PATH = ROOT / "deliverables" / "project.template.json"
DEFAULT_PROJECTS_DIR = ROOT / "projects"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_template() -> dict:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def ensure_dirs(project_root: Path) -> dict[str, Path]:
    paths = {
        "input": project_root / "input",
        "audio": project_root / "audio",
        "transcript": project_root / "transcript",
        "scene_plan": project_root / "scene_plan",
        "prompts": project_root / "prompts",
        "images_root": project_root / "images",
        "images_fastgen": project_root / "images" / "fastgen_run",
        "images_fastgen_raw": project_root / "images" / "fastgen_run" / "images",
        "images_normalized": project_root / "images" / "normalized",
        "video_runs": project_root / "video_runs",
        "renders": project_root / "renders",
        "motion": project_root / "motion",
        "qc": project_root / "qc",
        "publishing": project_root / "publishing",
        "publishing_thumbs": project_root / "publishing" / "thumbnails",
        "publishing_thumb_candidates": project_root / "publishing" / "thumbnails" / "candidates",
        "logs": project_root / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def infer_extension_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix:
        return suffix
    return ".mp3"


def infer_extension_from_headers(headers) -> str | None:
    content_type = headers.get_content_type()
    guessed = mimetypes.guess_extension(content_type)
    if guessed in {".jpe", ".jpeg"}:
        return ".jpg"
    return guessed


def stage_audio(audio_source: str, audio_dir: Path) -> Path:
    if audio_source.startswith(("http://", "https://")):
        req = urllib.request.Request(audio_source, headers={"User-Agent": "CodexFastgenOnly/1.0"})
        with urllib.request.urlopen(req) as response:
            ext = infer_extension_from_headers(response.headers) or infer_extension_from_url(audio_source)
            target = audio_dir / f"source_audio{ext}"
            with target.open("wb") as f:
                shutil.copyfileobj(response, f)
        return target

    source_path = Path(audio_source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Audio source not found: {source_path}")
    target = audio_dir / source_path.name
    if source_path != target:
        shutil.copy2(source_path, target)
    return target


def write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def create_publishing_scaffolds(publishing_dir: Path, thumbs_dir: Path) -> dict[str, Path]:
    title_drafts = publishing_dir / "title_drafts.json"
    description_drafts = publishing_dir / "description_drafts.json"
    title_approved = publishing_dir / "title_approved.txt"
    description_approved = publishing_dir / "description_approved.md"
    thumbnail_brief = publishing_dir / "thumbnail_brief.md"
    prompt_candidates = publishing_dir / "thumbnail_prompt_candidates.json"
    approved_prompt = publishing_dir / "thumbnail_prompt_approved.txt"
    approved_thumbnail = thumbs_dir / "approved.png"
    run_manifest = thumbs_dir / "run_manifest.json"

    write_if_missing(
        title_drafts,
        json.dumps(
            {
                "status": "draft",
                "prompt_version": "youtube-title-v1",
                "drafts": [],
                "selection_notes": "",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_if_missing(
        description_drafts,
        json.dumps(
            {
                "status": "draft",
                "prompt_version": "youtube-description-v1",
                "drafts": [],
                "selection_notes": "",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_if_missing(title_approved, "")
    write_if_missing(description_approved, "")
    write_if_missing(
        thumbnail_brief,
        "\n".join(
            [
                "# Thumbnail Brief",
                "",
                "Working angle:",
                "",
                "Primary promise/conflict:",
                "",
                "Main subject/person:",
                "",
                "Background/world:",
                "",
                "Emotion to communicate:",
                "",
                "Text on thumbnail (if any):",
                "",
                "Things to avoid:",
                "",
            ]
        )
        + "\n",
    )
    write_if_missing(
        prompt_candidates,
        json.dumps(
            {
                "status": "draft",
                "prompt_version": "youtube-thumbnail-v1",
                "candidates": [],
                "selection_notes": "",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_if_missing(approved_prompt, "")
    write_if_missing(run_manifest, "[]\n")

    return {
        "title_drafts": title_drafts,
        "description_drafts": description_drafts,
        "title_approved": title_approved,
        "description_approved": description_approved,
        "thumbnail_brief": thumbnail_brief,
        "prompt_candidates": prompt_candidates,
        "approved_prompt": approved_prompt,
        "approved_thumbnail": approved_thumbnail,
        "run_manifest": run_manifest,
    }


def create_project_manifest(
    project_id: str,
    project_root: Path,
    audio_path: Path,
    dirs: dict[str, Path],
    publishing_files: dict[str, Path],
    raw_text_path: Path | None,
) -> dict:
    manifest = load_template()
    now = iso_now()
    manifest["profile_id"] = "fastgen_only"
    manifest["project_id"] = project_id
    manifest["created_at"] = now
    manifest["updated_at"] = now
    manifest["status"] = "in_progress"
    manifest["current_stage"] = "transcribe"
    manifest["meta"]["project_root"] = str(project_root)
    manifest["meta"]["title"] = project_id

    raw_text_target = dirs["input"] / "raw_text.md"
    if raw_text_path:
        shutil.copy2(raw_text_path, raw_text_target)
        manifest["inputs"]["raw_text_path"] = str(raw_text_target)
        manifest["inputs"]["raw_text_char_count"] = len(raw_text_target.read_text(encoding="utf-8"))
        manifest["rewrite"]["status"] = "pending"
        manifest["rewrite"]["source_text_path"] = str(raw_text_target)
    else:
        manifest["inputs"]["raw_text_path"] = str(raw_text_target)
        manifest["inputs"]["raw_text_char_count"] = 0
        manifest["rewrite"]["status"] = "pending"
        manifest["rewrite"]["source_text_path"] = str(raw_text_target)

    manifest["rewrite"]["rewritten_script_path"] = str(dirs["input"] / "voice_script.md")
    manifest["rewrite"]["approved_script_path"] = str(dirs["input"] / "voice_script_approved.md")

    manifest["inputs"]["audio_path"] = str(audio_path)
    manifest["transcription"]["audio_path"] = str(audio_path)
    manifest["transcription"]["srt_path"] = str(dirs["transcript"] / f"{audio_path.stem}.srt")
    manifest["transcription"]["segments_json_path"] = str(dirs["transcript"] / f"{audio_path.stem}.segments.json")
    manifest["transcription"]["meta_json_path"] = str(dirs["transcript"] / f"{audio_path.stem}.meta.json")

    manifest["scene_plan"]["source_srt_path"] = manifest["transcription"]["srt_path"]
    manifest["scene_plan"]["long_segment_report_path"] = str(dirs["scene_plan"] / "long_segment_report.json")
    manifest["scene_plan"]["scene_plan_path"] = str(dirs["scene_plan"] / "scene_plan.json")

    manifest["prompts"]["prompt_export_path"] = str(dirs["scene_plan"] / "scene_prompts.md")
    manifest["prompts"]["prompt_package_path"] = str(dirs["prompts"] / "prompt_package.json")
    manifest["prompts"]["generator_ready_path"] = str(dirs["prompts"] / "fastgen_prompts_generator_ready.md")
    manifest["prompts"]["prompt_review_path"] = str(dirs["prompts"] / "prompt_review.md")

    manifest["images"]["run_manifest_path"] = str(dirs["images_fastgen"] / "run_manifest.json")
    manifest["images"]["selection_manifest_path"] = str(project_root / "qc" / "selection_manifest.json")
    manifest["images"]["raw_images_dir"] = str(dirs["images_fastgen_raw"])
    manifest["images"]["normalized_images_dir"] = str(dirs["images_normalized"])

    manifest["animation"]["status"] = "skipped"
    manifest["animation"]["policy_name"] = "disabled"
    manifest["animation"]["campaign_manifest_path"] = None
    manifest["animation"]["timeline_subset_path"] = None
    manifest["animation"]["provider"] = None
    manifest["animation"]["run_manifest_path"] = None
    manifest["animation"]["videos_dir"] = None
    manifest["animation"]["success_log_path"] = None
    manifest["animation"]["failed_log_path"] = None

    manifest["render"]["render_strategy"] = "images_only"
    manifest["render"]["mixed_manifest_path"] = str(dirs["renders"] / "mixed_manifest.json")
    manifest["render"]["motion_plan_path"] = str(project_root / "motion" / "motion_plan.json")
    manifest["render"]["slideshow_timeline_path"] = str(dirs["renders"] / "slideshow_timeline.json")
    manifest["render"]["ffconcat_path"] = str(dirs["renders"] / "timeline.ffconcat")
    manifest["render"]["final_video_path"] = str(dirs["renders"] / f"{project_id}.mp4")

    manifest["publishing"]["status"] = "pending"
    manifest["publishing"]["title_generation"]["drafts_path"] = str(publishing_files["title_drafts"])
    manifest["publishing"]["title_generation"]["approved_title_path"] = str(publishing_files["title_approved"])
    manifest["publishing"]["description_generation"]["drafts_path"] = str(publishing_files["description_drafts"])
    manifest["publishing"]["description_generation"]["approved_description_path"] = str(publishing_files["description_approved"])
    manifest["publishing"]["thumbnail_generation"]["thumbnail_brief_path"] = str(publishing_files["thumbnail_brief"])
    manifest["publishing"]["thumbnail_generation"]["prompt_candidates_path"] = str(publishing_files["prompt_candidates"])
    manifest["publishing"]["thumbnail_generation"]["approved_prompt_path"] = str(publishing_files["approved_prompt"])
    manifest["publishing"]["thumbnail_generation"]["run_manifest_path"] = str(publishing_files["run_manifest"])
    manifest["publishing"]["thumbnail_generation"]["candidates_dir"] = str(dirs["publishing_thumb_candidates"])
    manifest["publishing"]["thumbnail_generation"]["approved_thumbnail_path"] = str(publishing_files["approved_thumbnail"])

    manifest["qc"]["qc_report_path"] = str(dirs["logs"] / "qc_report.md")
    manifest["qc"]["results_json_path"] = str(project_root / "qc" / "qc_results.json")
    manifest["logs"]["pipeline_log_path"] = str(dirs["logs"] / "pipeline.log")
    manifest["logs"]["events_jsonl_path"] = str(dirs["logs"] / "events.jsonl")

    return manifest


def run_transcription(project_manifest_path: Path, manifest: dict, model: str, language: str, compute_type: str, device: str) -> None:
    audio_path = manifest["transcription"]["audio_path"]
    output_dir = Path(manifest["meta"]["project_root"]) / "transcript"
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "transcribe_faster_whisper.py"),
        audio_path,
        "--model",
        model,
        "--language",
        language,
        "--compute-type",
        compute_type,
        "--device",
        device,
        "--output-dir",
        str(output_dir),
    ]
    subprocess.run(cmd, check=True)

    meta_path = Path(manifest["transcription"]["meta_json_path"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    manifest["inputs"]["audio_duration_seconds"] = float(meta["duration"])
    manifest["transcription"]["status"] = "completed"
    manifest["current_stage"] = "scene_plan"
    manifest["updated_at"] = iso_now()
    project_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--audio-source", required=True, help="Local path or http(s) URL to the audio file.")
    parser.add_argument("--raw-text-path", help="Optional local path to the raw script text.")
    parser.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    parser.add_argument("--skip-transcribe", action="store_true")
    parser.add_argument("--whisper-model", default="base")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    projects_dir = Path(args.projects_dir)
    project_root = projects_dir / args.project_id
    dirs = ensure_dirs(project_root)

    raw_text_path = Path(args.raw_text_path).resolve() if args.raw_text_path else None
    audio_path = stage_audio(args.audio_source, dirs["audio"])
    publishing_files = create_publishing_scaffolds(dirs["publishing"], dirs["publishing_thumbs"])
    manifest = create_project_manifest(args.project_id, project_root, audio_path, dirs, publishing_files, raw_text_path)

    project_manifest_path = project_root / "project.json"
    project_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    write_if_missing(dirs["input"] / "raw_text.md", "")
    write_if_missing(dirs["input"] / "voice_script.md", "")
    write_if_missing(dirs["input"] / "voice_script_approved.md", "")

    if args.skip_transcribe:
        print(project_manifest_path)
        return

    run_transcription(
        project_manifest_path,
        manifest,
        model=args.whisper_model,
        language=args.language,
        compute_type=args.compute_type,
        device=args.device,
    )
    print(project_manifest_path)


if __name__ == "__main__":
    main()
