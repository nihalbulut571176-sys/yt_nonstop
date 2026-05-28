import argparse
import subprocess
import sys
from pathlib import Path

from project_pipeline_utils import (
    STAGE_SEQUENCE,
    append_event,
    append_log,
    load_project,
    mark_stage,
    normalize_stage_name,
    save_project,
    stage_index,
)


ROOT = Path(__file__).resolve().parents[1]


def stage_done(project: dict, stage: str) -> bool:
    stage = normalize_stage_name(stage)
    if stage == "transcription":
        return project["transcription"].get("status") == "completed"
    if stage == "cleanup_transcript_from_source":
        return project["transcript_cleanup"].get("status") in {"completed", "warning", "skipped_no_source"}
    if stage == "ingest_srt":
        return Path(project["planning"]["sentence_blocks_json_path"]).exists()
    if stage == "build_scene_map":
        scene_map_path = Path(project["planning"]["scene_map_path"])
        return scene_map_path.exists() and "\"semantic_units\"" in scene_map_path.read_text(encoding="utf-8")
    if stage == "expand_storyboard":
        return Path(project["planning"]["storyboard_path"]).exists()
    if stage == "build_reference_prompt_pack":
        return Path(project["prompts"]["reference_prompt_pack_path"]).exists()
    if stage == "generate_reference_images":
        return Path(project["prompts"]["reference_generation_manifest_path"]).exists()
    if stage == "build_subject_registry":
        return Path(project["prompts"]["subject_registry_path"]).exists()
    if stage == "build_continuity_map":
        return Path(project["planning"]["continuity_map_json_path"]).exists()
    if stage == "allocate_frames":
        return Path(project["scene_plan"]["scene_plan_path"]).exists()
    if stage == "build_narration_beats":
        return Path(project["planning"]["narration_beats_path"]).exists()
    if stage == "build_frame_briefs":
        return Path(project["planning"]["frame_briefs_json_path"]).exists()
    if stage == "attach_reference_assets":
        return Path(project["planning"]["reference_binding_report_path"]).exists()
    if stage == "generate_fastgen_prompt_drafts":
        return Path(project["prompts"]["final_scene_plan_path"]).exists()
    if stage == "generation_lock":
        return Path(project["prompts"]["generation_locked_json_path"]).exists()
    if stage == "quality_assurance":
        return Path(project["logs"]["qa_report_json_path"]).exists()
    if stage == "export_montage_map":
        return Path(project["exports"]["montage_timing_map_json_path"]).exists()
    if stage == "export_generation_batches":
        return Path(project["prompts"]["fastgen_export_path"]).exists()
    if stage == "report":
        return Path(project["logs"]["workflow_report_json_path"]).exists()
    if stage == "motion_plan":
        return Path(project["motion"]["motion_plan_json_path"]).exists()
    if stage == "final_review":
        return Path(project["logs"]["final_review_report_path"]).exists()
    if stage == "publishing_package":
        return project["publishing"].get("status") == "ready_for_generation"
    if stage == "generate_images":
        return project["images"].get("status") in {"generated", "normalized"}
    if stage == "image_qc":
        return Path(project["images"]["image_qc_report_path"]).exists() and Path(project["images"]["selected_images_manifest_path"]).exists()
    if stage == "normalize_images":
        return project["images"].get("status") == "normalized"
    if stage == "timeline":
        return project["render"].get("status") in {"timeline_built", "completed"}
    if stage == "render":
        return project["render"].get("status") == "completed" and Path(project["render"]["final_video_path"]).exists()
    raise KeyError(stage)


def build_stage_command(project: dict, project_json: Path, stage: str, args: argparse.Namespace) -> list[str]:
    stage = normalize_stage_name(stage)
    if stage == "transcription":
        source_text_path = project.get("inputs", {}).get("raw_text_path")
        return [
            sys.executable,
            str(ROOT / "scripts" / "transcribe_faster_whisper.py"),
            project["transcription"]["audio_path"],
            "--model",
            project["transcription"]["model"],
            "--language",
            project["transcription"].get("requested_language") or project["meta"]["language"],
            "--compute-type",
            project["transcription"].get("compute_type", "int8"),
            "--device",
            project["transcription"]["device"],
            "--output-dir",
            str(Path(project["transcription"]["srt_path"]).parent),
        ] + (["--initial-prompt-file", source_text_path] if source_text_path and Path(source_text_path).exists() else [])
    command_map = {
        "cleanup_transcript_from_source": [sys.executable, str(ROOT / "scripts" / "cleanup_transcript_from_source.py"), "--project-json", str(project_json)],
        "ingest_srt": [sys.executable, str(ROOT / "scripts" / "ingest_srt.py"), "--project-json", str(project_json)],
        "build_scene_map": [sys.executable, str(ROOT / "scripts" / "build_scene_map.py"), "--project-json", str(project_json)],
        "expand_storyboard": [sys.executable, str(ROOT / "scripts" / "expand_storyboard.py"), "--project-json", str(project_json)],
        "build_reference_prompt_pack": [sys.executable, str(ROOT / "scripts" / "build_reference_prompt_pack.py"), "--project-json", str(project_json)],
        "generate_reference_images": [
            sys.executable,
            str(ROOT / "scripts" / "generate_reference_images.py"),
            "--project-json",
            str(project_json),
            "--size",
            args.reference_image_size,
            "--aspect-ratio",
            args.reference_aspect_ratio,
            "--poll-seconds",
            str(args.poll_seconds),
            "--max-polls",
            str(args.max_polls),
            "--concurrency",
            str(args.reference_concurrency),
        ],
        "build_subject_registry": [sys.executable, str(ROOT / "scripts" / "build_subject_registry.py"), "--project-json", str(project_json)],
        "build_continuity_map": [sys.executable, str(ROOT / "scripts" / "build_project_continuity_bible.py"), "--project-json", str(project_json)],
        "allocate_frames": [sys.executable, str(ROOT / "scripts" / "allocate_frames.py"), "--project-json", str(project_json)],
        "build_narration_beats": [sys.executable, str(ROOT / "scripts" / "build_narration_beats.py"), "--project-json", str(project_json)],
        "build_frame_briefs": [sys.executable, str(ROOT / "scripts" / "build_frame_briefs.py"), "--project-json", str(project_json)],
        "attach_reference_assets": [sys.executable, str(ROOT / "scripts" / "attach_reference_assets.py"), "--project-json", str(project_json)],
        "generate_fastgen_prompt_drafts": [sys.executable, str(ROOT / "scripts" / "apply_llm_prompt_drafts.py"), "--project-json", str(project_json)],
        "generation_lock": [sys.executable, str(ROOT / "scripts" / "generation_lock.py"), "--project-json", str(project_json)],
        "quality_assurance": [sys.executable, str(ROOT / "scripts" / "validate_project.py"), "--project-json", str(project_json), "--stage", "quality_assurance"],
        "export_montage_map": [sys.executable, str(ROOT / "scripts" / "export_montage_map.py"), "--project-json", str(project_json)],
        "export_generation_batches": [sys.executable, str(ROOT / "scripts" / "export_generation_batches.py"), "--project-json", str(project_json)],
        "report": [sys.executable, str(ROOT / "scripts" / "build_workflow_report.py"), "--project-json", str(project_json)],
        "motion_plan": [sys.executable, str(ROOT / "scripts" / "build_project_motion_plan.py"), "--project-json", str(project_json)],
        "final_review": [sys.executable, str(ROOT / "scripts" / "run_final_review.py"), "--project-json", str(project_json)],
        "publishing_package": [sys.executable, str(ROOT / "scripts" / "prepare_project_publishing_package.py"), "--project-json", str(project_json)],
        "image_qc": [sys.executable, str(ROOT / "scripts" / "qc_generated_images.py"), "--project-json", str(project_json)],
        "normalize_images": [
            sys.executable,
            str(ROOT / "scripts" / "normalize_project_images.py"),
            "--project-json",
            str(project_json),
            "--width",
            str(args.width),
            "--height",
            str(args.height),
        ],
        "timeline": [sys.executable, str(ROOT / "scripts" / "build_project_slideshow_timeline.py"), "--project-json", str(project_json)],
        "render": [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "render_project_slideshow_video.ps1"),
            "-ProjectJson",
            str(project_json),
        ],
    }
    if stage == "generate_images":
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_project_fastgen_generation.py"),
            "--project-json",
            str(project_json),
            "--size",
            args.image_size,
            "--poll-seconds",
            str(args.poll_seconds),
            "--max-polls",
            str(args.max_polls),
            "--concurrency",
            str(args.concurrency),
        ]
        if args.image_retry_rounds:
            cmd.extend(["--retry-rounds", str(args.image_retry_rounds)])
        if args.soften_policy_prompts:
            cmd.append("--soften-policy-prompts")
        return cmd
    return command_map[stage]


def post_stage_update(project_json: Path, stage: str) -> None:
    stage = normalize_stage_name(stage)
    project = load_project(project_json)
    if stage == "transcription":
        meta_path = Path(project["transcription"]["meta_json_path"])
        if meta_path.exists():
            import json

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            project["inputs"]["audio_duration_seconds"] = float(meta.get("duration", 0) or 0)
            detected_language = str(meta.get("language", "")).strip().lower()
            if detected_language:
                project["meta"]["language"] = detected_language
        project["transcription"]["status"] = "completed"
        project["current_stage"] = "cleanup_transcript_from_source"
    elif stage == "cleanup_transcript_from_source":
        project["current_stage"] = "ingest_srt"
    elif stage == "build_continuity_map":
        project["current_stage"] = "build_reference_prompt_pack"
    elif stage == "build_reference_prompt_pack":
        project["current_stage"] = "generate_reference_images"
    elif stage == "generate_reference_images":
        project["current_stage"] = "build_subject_registry"
    elif stage == "build_subject_registry":
        project["current_stage"] = "allocate_frames"
    elif stage == "allocate_frames":
        project["current_stage"] = "build_narration_beats"
    elif stage == "build_narration_beats":
        project["current_stage"] = "build_frame_briefs"
    elif stage == "build_frame_briefs":
        project["current_stage"] = "attach_reference_assets"
    elif stage == "attach_reference_assets":
        project["current_stage"] = "generate_fastgen_prompt_drafts"
    elif stage == "generate_fastgen_prompt_drafts":
        project["current_stage"] = "generation_lock"
    elif stage == "generation_lock":
        project["current_stage"] = "quality_assurance"
    elif stage == "quality_assurance":
        project["current_stage"] = "export_montage_map"
    elif stage == "export_montage_map":
        project["current_stage"] = "export_generation_batches"
    elif stage == "export_generation_batches":
        project["current_stage"] = "report"
    elif stage == "report":
        project["current_stage"] = "motion_plan"
    elif stage == "publishing_package":
        project["publishing"]["status"] = "ready_for_generation"
        project["current_stage"] = "generate_images"
    elif stage == "generate_images":
        project["current_stage"] = "image_qc"
    elif stage == "image_qc":
        project["current_stage"] = "normalize_images"
    elif stage == "render":
        project["render"]["status"] = "completed"
        project["status"] = "completed"
        project["current_stage"] = "done"
    save_project(project_json, project)


def validate_stage(project_json: Path, validation_stage: str, dry_run: bool) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / "validate_project.py"), "--project-json", str(project_json), "--stage", validation_stage]
    if dry_run:
        print("DRY-RUN VALIDATE:", " ".join(cmd))
        return
    subprocess.run(cmd, check=True)


def next_resume_stage(project: dict) -> str:
    for stage in STAGE_SEQUENCE:
        if not stage_done(project, stage):
            return stage
    return STAGE_SEQUENCE[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    stage_choices = STAGE_SEQUENCE + ["generate_fastgen_prompts", "scene_context_pack"]
    parser.add_argument("--from", dest="from_stage", choices=stage_choices)
    parser.add_argument("--to", dest="to_stage", choices=stage_choices, default="render")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--auto-author-llm",
        dest="auto_author_llm",
        action="store_true",
        help="Auto-author FastGen prompt drafts with the Codex/LLM stage.",
    )
    parser.add_argument(
        "--no-auto-author-llm",
        dest="auto_author_llm",
        action="store_false",
        help="Skip the internal LLM authoring pass and expect prompt drafts to exist already.",
    )
    parser.add_argument("--require-filled-prompts", action="store_true")
    parser.add_argument("--image-size", default="1024x1024")
    parser.add_argument("--reference-image-size", default="1024x1536")
    parser.add_argument("--reference-aspect-ratio", default="2:3")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--reference-concurrency", type=int, default=10)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--image-retry-rounds", type=int, default=3)
    parser.add_argument("--soften-policy-prompts", action="store_true")
    parser.set_defaults(auto_author_llm=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    start_stage = normalize_stage_name(args.from_stage) if args.from_stage else (next_resume_stage(project) if args.resume else STAGE_SEQUENCE[0])
    end_stage = normalize_stage_name(args.to_stage)
    selected_stages = STAGE_SEQUENCE[stage_index(start_stage) : stage_index(end_stage) + 1]

    append_log(project, f"SRT-first pipeline run requested: {selected_stages}")
    append_event(project, {"kind": "pipeline_start", "stages": selected_stages})

    validation_map = {
        "transcription": "transcription",
        "cleanup_transcript_from_source": "transcript_quality",
        "ingest_srt": "ingest_srt",
        "build_scene_map": "build_scene_map",
        "expand_storyboard": "expand_storyboard",
        "build_reference_prompt_pack": "build_reference_prompt_pack",
        "generate_reference_images": "generate_reference_images",
        "build_subject_registry": "build_subject_registry",
        "build_continuity_map": "build_continuity_map",
        "allocate_frames": "allocate_frames",
        "build_narration_beats": "build_narration_beats",
        "build_frame_briefs": "build_frame_briefs",
        "attach_reference_assets": "attach_reference_assets",
        "generate_fastgen_prompt_drafts": "generate_fastgen_prompt_drafts",
        "generation_lock": "generation_lock",
        "export_montage_map": "export_montage_map",
        "export_generation_batches": "export_generation_batches",
        "report": "report",
        "motion_plan": "motion_plan",
        "final_review": "final_review",
        "generate_images": "images",
        "image_qc": "images",
        "normalize_images": "normalized_images",
        "timeline": "timeline",
        "render": "render",
    }

    try:
        for stage in selected_stages:
            project = load_project(project_json)
            if args.resume and stage_done(project, stage):
                append_log(project, f"Skipping completed stage during resume: {stage}")
                continue

            if stage == "generate_fastgen_prompt_drafts":
                context_cmd = [
                    sys.executable,
                    str(ROOT / "scripts" / "build_scene_context_pack.py"),
                    "--project-json",
                    str(project_json),
                ]
                append_log(project, f"Building scene context pack: {' '.join(context_cmd)}")
                if args.dry_run:
                    print("DRY-RUN:", " ".join(context_cmd))
                else:
                    subprocess.run(context_cmd, check=True)
                    validate_stage(project_json, "scene_context_pack", args.dry_run)
            if stage == "generate_fastgen_prompt_drafts" and args.auto_author_llm:
                auto_cmd = [
                    sys.executable,
                    str(ROOT / "scripts" / "auto_author_llm_prompts.py"),
                    "--project-json",
                    str(project_json),
                ]
                append_log(project, f"Auto-authoring LLM prompt files: {' '.join(auto_cmd)}")
                if args.dry_run:
                    print("DRY-RUN:", " ".join(auto_cmd))
                else:
                    subprocess.run(auto_cmd, check=True)

            cmd = build_stage_command(project, project_json, stage, args)
            append_log(project, f"Running stage {stage}: {' '.join(cmd)}")
            append_event(project, {"kind": "stage_dispatch", "stage": stage, "command": cmd})
            mark_stage(project, stage, "running", current_stage=stage)
            save_project(project_json, project)

            if args.dry_run:
                print("DRY-RUN:", " ".join(cmd))
            else:
                subprocess.run(cmd, check=True)
                post_stage_update(project_json, stage)

            validation_stage = validation_map.get(stage)
            if validation_stage:
                validate_stage(project_json, validation_stage, args.dry_run)

        project = load_project(project_json)
        append_event(project, {"kind": "pipeline_end", "status": "success"})
        append_log(project, "SRT-first pipeline run completed successfully")
    except subprocess.CalledProcessError as exc:
        project = load_project(project_json)
        project["status"] = "failed"
        append_event(project, {"kind": "pipeline_end", "status": "failed", "returncode": exc.returncode})
        append_log(project, f"Pipeline failed with return code {exc.returncode}")
        save_project(project_json, project)
        raise


if __name__ == "__main__":
    main()
