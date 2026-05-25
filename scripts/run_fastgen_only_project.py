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
    save_project,
    stage_index,
)


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")


def stage_done(project: dict, stage: str) -> bool:
    if stage == "transcription":
        return project["transcription"].get("status") == "completed"
    if stage == "cleanup_transcript_from_source":
        return project["transcript_cleanup"].get("status") in {"completed", "warning", "skipped_no_source"}
    if stage == "scene_plan":
        return Path(project["scene_plan"]["scene_plan_path"]).exists()
    if stage == "scene_qa":
        return Path(project["logs"]["scene_qa_report_path"]).exists()
    if stage == "narrative_enrichment":
        return Path(project["scene_plan"]["scene_plan_path"]).exists() and Path(project["scene_plan"]["scene_plan_path"]).read_text(encoding="utf-8").find("\"narrative_purpose\"") >= 0
    if stage == "style_bible":
        return Path(project["prompts"]["style_guide_path"]).exists() and Path(project["prompts"]["visual_bible_path"]).exists()
    if stage == "visual_direction":
        return Path(project["logs"]["visual_direction_report_path"]).exists()
    if stage == "continuity_pass":
        return (Path(project["meta"]["project_root"]) / "config" / "continuity_bible.md").exists()
    if stage == "prompt_package":
        return Path(project["prompts"]["prompt_package_path"]).exists()
    if stage == "scene_context_pack":
        return Path(project["prompts"]["scene_context_pack_path"]).exists()
    if stage == "llm_prompt_drafts":
        return Path(project["prompts"]["llm_prompt_drafts_path"]).exists()
    if stage == "prompt_qa":
        return Path(project["logs"]["prompt_qa_report_path"]).exists()
    if stage == "apply_llm_prompt_drafts":
        return Path(project["prompts"]["final_scene_plan_path"]).exists()
    if stage == "motion_plan":
        return Path(project["motion"]["motion_plan_json_path"]).exists()
    if stage == "export_prompts":
        return Path(project["prompts"]["fastgen_export_path"]).exists()
    if stage == "final_review":
        return Path(project["logs"]["final_review_report_path"]).exists()
    if stage == "publishing_package":
        return project["publishing"].get("status") == "ready_for_generation"
    if stage == "generate_images":
        return project["images"].get("status") in {"generated", "normalized"}
    if stage == "normalize_images":
        return project["images"].get("status") == "normalized"
    if stage == "timeline":
        return project["render"].get("status") in {"timeline_built", "completed"}
    if stage == "render":
        return project["render"].get("status") == "completed" and Path(project["render"]["final_video_path"]).exists()
    raise KeyError(stage)


def build_stage_command(project: dict, project_json: Path, stage: str, args: argparse.Namespace) -> list[str]:
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
        "scene_plan": [sys.executable, str(ROOT / "scripts" / "build_project_scene_plan.py"), "--project-json", str(project_json)],
        "scene_qa": [sys.executable, str(ROOT / "scripts" / "run_scene_qa.py"), "--project-json", str(project_json)],
        "narrative_enrichment": [sys.executable, str(ROOT / "scripts" / "build_project_narrative_map.py"), "--project-json", str(project_json)],
        "style_bible": [sys.executable, str(ROOT / "scripts" / "build_project_style_bible.py"), "--project-json", str(project_json)],
        "visual_direction": [sys.executable, str(ROOT / "scripts" / "build_project_visual_direction.py"), "--project-json", str(project_json)],
        "continuity_pass": [sys.executable, str(ROOT / "scripts" / "build_project_continuity_bible.py"), "--project-json", str(project_json)],
        "prompt_package": [sys.executable, str(ROOT / "scripts" / "build_project_prompt_package.py"), "--project-json", str(project_json)],
        "scene_context_pack": [sys.executable, str(ROOT / "scripts" / "build_scene_context_pack.py"), "--project-json", str(project_json)],
        "prompt_qa": [sys.executable, str(ROOT / "scripts" / "run_prompt_qa.py"), "--project-json", str(project_json)],
        "apply_llm_prompt_drafts": [sys.executable, str(ROOT / "scripts" / "apply_llm_prompt_drafts.py"), "--project-json", str(project_json)],
        "motion_plan": [sys.executable, str(ROOT / "scripts" / "build_project_motion_plan.py"), "--project-json", str(project_json)],
        "final_review": [sys.executable, str(ROOT / "scripts" / "run_final_review.py"), "--project-json", str(project_json)],
        "publishing_package": [sys.executable, str(ROOT / "scripts" / "prepare_project_publishing_package.py"), "--project-json", str(project_json)],
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
    if stage == "llm_prompt_drafts":
        return [sys.executable, str(ROOT / "scripts" / "validate_project.py"), "--project-json", str(project_json), "--stage", "llm_prompt_drafts"]
    if stage == "export_prompts":
        cmd = [sys.executable, str(ROOT / "scripts" / "export_project_fastgen_prompts.py"), "--project-json", str(project_json)]
        if args.require_filled_prompts:
            cmd.append("--require-filled-prompts")
        return cmd
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
        project["current_stage"] = "scene_plan"
    elif stage == "scene_context_pack":
        project["prompts"]["status"] = "context_ready"
        project["current_stage"] = "llm_prompt_drafts"
    elif stage == "llm_prompt_drafts":
        project["current_stage"] = "prompt_qa"
    elif stage == "publishing_package":
        project["publishing"]["status"] = "ready_for_generation"
        project["current_stage"] = "generate_images"
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
    parser.add_argument("--from", dest="from_stage", choices=STAGE_SEQUENCE)
    parser.add_argument("--to", dest="to_stage", choices=STAGE_SEQUENCE, default="render")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auto-author-llm", action="store_true")
    parser.add_argument("--require-filled-prompts", action="store_true")
    parser.add_argument("--image-size", default="1024x1024")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--image-retry-rounds", type=int, default=3)
    parser.add_argument("--soften-policy-prompts", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    start_stage = args.from_stage or (next_resume_stage(project) if args.resume else STAGE_SEQUENCE[0])
    end_stage = args.to_stage
    selected_stages = STAGE_SEQUENCE[stage_index(start_stage) : stage_index(end_stage) + 1]

    append_log(project, f"SRT-first pipeline run requested: {selected_stages}")
    append_event(project, {"kind": "pipeline_start", "stages": selected_stages})

    validation_map = {
        "transcription": "transcription",
        "cleanup_transcript_from_source": "transcript_quality",
        "scene_plan": "scene_plan",
        "scene_qa": "scene_qa",
        "prompt_package": "prompt_package",
        "scene_context_pack": "scene_context_pack",
        "llm_prompt_drafts": "llm_prompt_drafts",
        "prompt_qa": "prompt_qa",
        "export_prompts": "export_prompts",
        "motion_plan": "motion_plan",
        "final_review": "final_review",
        "generate_images": "images",
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

            if stage == "llm_prompt_drafts" and args.auto_author_llm:
                drafts_path = Path(project["prompts"].get("llm_prompt_drafts_path") or "")
                if not drafts_path.exists():
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
