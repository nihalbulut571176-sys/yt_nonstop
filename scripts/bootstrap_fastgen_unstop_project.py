import argparse
import json
from pathlib import Path

from bootstrap_fastgen_only_project import (
    DEFAULT_PROJECTS_DIR,
    create_publishing_scaffolds,
    ensure_dirs,
    infer_language_from_text,
    iso_now,
    load_template,
    run_transcription,
    stage_audio,
    write_if_missing,
)


def create_project_manifest(
    project_id: str,
    project_root: Path,
    audio_path: Path,
    dirs: dict[str, Path],
    publishing_files: dict[str, Path],
    raw_text_path: Path | None,
    whisper_model: str,
    language: str,
    compute_type: str,
    device: str,
) -> dict:
    manifest = load_template()
    now = iso_now()
    manifest["profile_id"] = "fastgen_unstop"
    manifest["project_id"] = project_id
    manifest["created_at"] = now
    manifest["updated_at"] = now
    manifest["status"] = "in_progress"
    manifest["current_stage"] = "transcribe"
    manifest["meta"]["project_root"] = str(project_root)
    manifest["meta"]["title"] = project_id
    manifest["meta"]["language"] = language

    raw_text_target = dirs["input"] / "raw_text.md"
    if raw_text_path:
        raw_text_target.write_text(raw_text_path.read_text(encoding="utf-8-sig"), encoding="utf-8")
        manifest["inputs"]["raw_text_path"] = str(raw_text_target)
        manifest["inputs"]["raw_text_char_count"] = len(raw_text_target.read_text(encoding="utf-8"))
    else:
        manifest["inputs"]["raw_text_path"] = str(raw_text_target)
        manifest["inputs"]["raw_text_char_count"] = 0

    manifest["rewrite"]["status"] = "pending"
    manifest["rewrite"]["source_text_path"] = str(raw_text_target)
    manifest["rewrite"]["rewritten_script_path"] = str(dirs["input"] / "voice_script.md")
    manifest["rewrite"]["approved_script_path"] = str(dirs["input"] / "voice_script_approved.md")

    manifest["inputs"]["audio_path"] = str(audio_path)
    manifest["transcription"]["model"] = whisper_model
    manifest["transcription"]["requested_language"] = language
    manifest["transcription"]["compute_type"] = compute_type
    manifest["transcription"]["device"] = device
    manifest["transcription"]["audio_path"] = str(audio_path)
    manifest["transcription"]["srt_path"] = str(dirs["transcript"] / f"{audio_path.stem}.srt")
    manifest["transcription"]["segments_json_path"] = str(dirs["transcript"] / f"{audio_path.stem}.segments.json")
    manifest["transcription"]["meta_json_path"] = str(dirs["transcript"] / f"{audio_path.stem}.meta.json")

    manifest["transcript_cleanup"]["source_text_path"] = str(raw_text_target)
    manifest["transcript_cleanup"]["used_source_path"] = None
    manifest["transcript_cleanup"]["cleaned_srt_path"] = str(dirs["transcript"] / "cleaned.srt")
    manifest["transcript_cleanup"]["cleaned_segments_json_path"] = str(dirs["transcript"] / "cleaned_segments.json")
    manifest["transcript_cleanup"]["cleaned_timed_transcript_md_path"] = str(dirs["transcript"] / "cleaned_timed_transcript.md")
    manifest["transcript_cleanup"]["cleanup_report_path"] = str(dirs["transcript"] / "cleanup_report.json")

    manifest["scene_plan"]["source_srt_path"] = manifest["transcription"]["srt_path"]
    manifest["scene_plan"]["long_segment_report_path"] = str(dirs["scene_plan"] / "long_segment_report.json")
    manifest["scene_plan"]["scene_plan_path"] = str(dirs["scene_plan"] / "scene_plan.json")

    manifest["prompts"]["prompt_export_path"] = str(dirs["scene_plan"] / "scene_prompts.md")
    manifest["prompts"]["style_guide_path"] = str(dirs["prompts"] / "style_guide.json")
    manifest["prompts"]["visual_shot_plan_path"] = str(dirs["prompts"] / "visual_shot_plan.json")
    manifest["prompts"]["shot_prompt_package_path"] = str(dirs["prompts"] / "shot_prompt_package.json")
    manifest["prompts"]["shot_prompt_review_path"] = str(dirs["prompts"] / "shot_prompt_review.md")
    manifest["prompts"]["prompt_package_path"] = str(dirs["prompts"] / "prompt_package.json")
    manifest["prompts"]["generator_ready_path"] = str(dirs["prompts"] / "fastgen_prompts_generator_ready.md")
    manifest["prompts"]["prompt_review_path"] = str(dirs["prompts"] / "prompt_review.md")

    manifest["images"]["run_manifest_path"] = str(dirs["images_fastgen"] / "run_manifest.json")
    manifest["images"]["raw_images_dir"] = str(dirs["images_fastgen_raw"])
    manifest["images"]["normalized_images_dir"] = str(dirs["images_normalized"])

    manifest["animation"]["status"] = "pending"
    manifest["animation"]["policy_name"] = "all_scenes_image_to_video"
    manifest["animation"]["campaign_manifest_path"] = str(dirs["video_runs"] / "campaign_manifest.json")
    manifest["animation"]["timeline_subset_path"] = str(dirs["video_runs"] / "scene_timeline.json")
    manifest["animation"]["provider"] = "veononstop"
    manifest["animation"]["run_manifest_path"] = str(dirs["video_runs"] / "run_manifest.json")
    manifest["animation"]["videos_dir"] = str(dirs["video_runs"] / "videos")
    manifest["animation"]["success_log_path"] = str(dirs["video_runs"] / "success.jsonl")
    manifest["animation"]["failed_log_path"] = str(dirs["video_runs"] / "failed.jsonl")

    manifest["render"]["render_strategy"] = "videos_only"
    manifest["render"]["mixed_manifest_path"] = str(dirs["renders"] / "video_manifest.json")
    manifest["render"]["slideshow_timeline_path"] = str(dirs["renders"] / "video_timeline.json")
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

    manifest["qc"]["qc_report_path"] = str(dirs["renders"] / "qc_report.json")
    manifest["logs"]["pipeline_log_path"] = str(dirs["logs"] / "pipeline.log")
    manifest["logs"]["events_jsonl_path"] = str(dirs["logs"] / "events.jsonl")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--audio-source", required=True, help="Local path or http(s) URL to the audio file.")
    parser.add_argument("--raw-text-path")
    parser.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    parser.add_argument("--skip-transcribe", action="store_true")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    projects_dir = Path(args.projects_dir)
    project_root = projects_dir / args.project_id
    dirs = ensure_dirs(project_root)

    raw_text_path = Path(args.raw_text_path).resolve() if args.raw_text_path else None
    effective_language = args.language
    if raw_text_path and raw_text_path.exists() and str(args.language).strip().lower() in {"", "auto", "none"}:
        effective_language = infer_language_from_text(raw_text_path.read_text(encoding="utf-8-sig"))

    audio_path = stage_audio(args.audio_source, dirs["audio"])
    publishing_files = create_publishing_scaffolds(dirs["publishing"], dirs["publishing_thumbs"])
    manifest = create_project_manifest(
        args.project_id,
        project_root,
        audio_path,
        dirs,
        publishing_files,
        raw_text_path,
        whisper_model=args.whisper_model,
        language=effective_language,
        compute_type=args.compute_type,
        device=args.device,
    )

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
        language=effective_language,
        compute_type=args.compute_type,
        device=args.device,
    )
    print(project_manifest_path)


if __name__ == "__main__":
    main()
