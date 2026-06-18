from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from yt_nonstop.pipeline.artifact_paths import STAGE_SEQUENCE, normalize_stage_name, stage_index
from yt_nonstop.pipeline.pilot_profiles import active_profile_name, apply_runtime_profile, effective_limit_frames, resolve_runtime_profile
from yt_nonstop.pipeline.project_config import append_event, append_log, load_project, mark_stage, save_project
from yt_nonstop.state.pipeline_state import (
    connect as connect_state_db,
    get_stage_state,
    mark_stage_completed,
    mark_stage_failed,
    mark_stage_running,
    resolve_stale_stages,
    resolve_state_db_path,
)


ROOT = Path(__file__).resolve().parents[3]


def _file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _path_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    if path.is_file():
        stat = path.stat()
        return {
            "path": str(path),
            "exists": True,
            "kind": "file",
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": _file_hash(path),
        }
    files = []
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        stat = child.stat()
        files.append({"relative": child.relative_to(path).as_posix(), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return {"path": str(path), "exists": True, "kind": "dir", "files": files}


def _stable_project_context(payload: Any) -> Any:
    if isinstance(payload, dict):
        filtered: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"updated_at", "last_result"}:
                continue
            if key == "state":
                continue
            if key == "current_stage":
                continue
            filtered[key] = _stable_project_context(value)
        return filtered
    if isinstance(payload, list):
        return [_stable_project_context(item) for item in payload]
    return payload


def stage_done(project: dict[str, Any], stage: str) -> bool:
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
        return project["planning"].get("narration_beats_status") in {"skeleton_built", "authored"} and Path(project["planning"]["narration_beats_path"]).exists()
    if stage == "author_narration_beats":
        return project["planning"].get("narration_beats_status") == "authored" and Path(project["planning"]["narration_beats_path"]).exists()
    if stage == "build_visual_shot_plan":
        return Path(project["prompts"]["visual_shot_plan_path"]).exists()
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


def _runtime_time_range_from_args(args: argparse.Namespace) -> dict[str, Any]:
    start_sec = getattr(args, "start_sec", None)
    end_sec = getattr(args, "end_sec", None)
    if start_sec is None and end_sec is None:
        return {}
    if start_sec is None or end_sec is None:
        raise ValueError("--start-sec and --end-sec must be provided together")
    start = max(0.0, float(start_sec))
    end = float(end_sec)
    if end <= start:
        raise ValueError("--end-sec must be greater than --start-sec")
    return {
        "enabled": True,
        "start_sec": round(start, 3),
        "end_sec": round(end, 3),
        "duration_sec": round(end - start, 3),
    }


def stage_output_paths(project: dict[str, Any], stage: str) -> list[Path]:
    stage = normalize_stage_name(stage)
    planning = project.get("planning", {})
    prompts = project.get("prompts", {})
    exports = project.get("exports", {})
    logs = project.get("logs", {})
    motion = project.get("motion", {})
    images = project.get("images", {})
    render = project.get("render", {})
    stage_to_paths = {
        "transcription": [Path(project["transcription"]["raw_srt_path"])],
        "cleanup_transcript_from_source": [Path(project["transcript_cleanup"]["cleaned_srt_path"])],
        "ingest_srt": [Path(planning["sentence_blocks_json_path"])],
        "build_scene_map": [Path(planning["scene_map_path"])],
        "expand_storyboard": [Path(planning["storyboard_path"])],
        "build_continuity_map": [Path(planning["continuity_map_json_path"])],
        "build_reference_prompt_pack": [Path(prompts["reference_prompt_pack_path"])],
        "generate_reference_images": [Path(prompts["reference_generation_manifest_path"])],
        "build_subject_registry": [Path(prompts["subject_registry_path"]), Path(prompts["entity_registry_path"])],
        "allocate_frames": [Path(project["scene_plan"]["scene_plan_path"]), Path(planning["visual_allocation_plan_path"])],
        "build_narration_beats": [Path(planning["narration_beats_path"])],
        "author_narration_beats": [Path(planning["narration_beats_path"])],
        "build_visual_shot_plan": [Path(prompts["visual_shot_plan_path"])],
        "build_frame_briefs": [Path(planning["frame_briefs_json_path"]), Path(prompts["prompt_package_path"])],
        "attach_reference_assets": [Path(planning["reference_binding_report_path"])],
        "generate_fastgen_prompt_drafts": [Path(prompts["llm_prompt_drafts_path"]), Path(prompts["final_scene_plan_path"])],
        "generation_lock": [Path(prompts["generation_locked_json_path"])],
        "quality_assurance": [Path(logs["qa_report_json_path"])],
        "export_montage_map": [Path(exports["montage_timing_map_json_path"])],
        "export_generation_batches": [Path(prompts["fastgen_export_path"]), Path(f'{prompts["fastgen_export_path"]}.meta.json')],
        "report": [Path(logs["workflow_report_json_path"])],
        "motion_plan": [Path(motion["motion_plan_json_path"])],
        "final_review": [Path(logs["final_review_report_path"])],
        "generate_images": [Path(images["run_manifest_path"]), Path(images["raw_images_dir"])],
        "image_qc": [Path(images["image_qc_report_path"]), Path(images["selected_images_manifest_path"])],
        "normalize_images": [Path(images["normalized_images_dir"]), Path(images["selected_images_manifest_path"])],
        "timeline": [Path(render["slideshow_timeline_path"]), Path(render["edit_decision_list_path"]), Path(render["ffconcat_path"])],
        "render": [Path(render["render_report_json_path"]), Path(render["final_video_path"])],
    }
    return stage_to_paths.get(stage, [])


def stage_output_markers(project: dict[str, Any], stage: str) -> dict[str, Any]:
    stage = normalize_stage_name(stage)
    markers = {
        "build_narration_beats": {"narration_beats_status": project["planning"].get("narration_beats_status")},
        "author_narration_beats": {"narration_beats_status": project["planning"].get("narration_beats_status")},
        "publishing_package": {"publishing_status": project["publishing"].get("status")},
        "generate_images": {"images_status": project["images"].get("status")},
        "normalize_images": {"images_status": project["images"].get("status")},
        "timeline": {"render_status": project["render"].get("status")},
        "render": {"render_status": project["render"].get("status")},
    }
    return markers.get(stage, {})


def compute_stage_output_hash(project: dict[str, Any], stage: str) -> tuple[str, bool]:
    payload = {"stage": normalize_stage_name(stage), "artifacts": [], "markers": stage_output_markers(project, stage)}
    output_exists = True
    for path in stage_output_paths(project, stage):
        fingerprint = _path_fingerprint(path)
        payload["artifacts"].append(fingerprint)
        output_exists = output_exists and bool(fingerprint.get("exists"))
    if not payload["artifacts"] and not payload["markers"]:
        payload["markers"] = {"current_stage": project.get("current_stage", ""), "status": project.get("status", "")}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest, output_exists


def compute_stage_input_hash(project_json: Path, project: dict[str, Any], stage: str) -> str:
    normalized_stage = normalize_stage_name(stage)
    upstream = []
    for upstream_stage in STAGE_SEQUENCE[: stage_index(normalized_stage)]:
        output_hash, output_exists = compute_stage_output_hash(project, upstream_stage)
        upstream.append({"stage": upstream_stage, "output_hash": output_hash, "output_exists": output_exists})
    payload = {
        "project_context": _stable_project_context(project),
        "stage": normalized_stage,
        "upstream": upstream,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def stage_hash_snapshot(project_json: Path, project: dict[str, Any], stages: list[str]) -> list[dict[str, Any]]:
    rows = []
    for stage in stages:
        output_hash, output_exists = compute_stage_output_hash(project, stage)
        rows.append(
            {
                "stage_name": stage,
                "input_hash": compute_stage_input_hash(project_json, project, stage),
                "output_hash": output_hash,
                "output_exists": output_exists and stage_done(project, stage),
            }
        )
    return rows


def build_stage_command(project: dict[str, Any], project_json: Path, stage: str, args: argparse.Namespace) -> list[str]:
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
        "author_narration_beats": [sys.executable, str(ROOT / "scripts" / "author_narration_beats.py"), "--project-json", str(project_json)],
        "build_visual_shot_plan": [sys.executable, str(ROOT / "scripts" / "build_visual_shot_plan.py"), "--project-json", str(project_json)],
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
        if args.resume:
            cmd.append("--resume")
        if args.retry_failed_only:
            cmd.append("--retry-failed-only")
        if args.state_db:
            cmd.extend(["--state-db", args.state_db])
        if getattr(args, "profile", ""):
            cmd.extend(["--profile", args.profile])
        if getattr(args, "real_generation", False):
            cmd.append("--real-generation")
        if int(getattr(args, "limit_frames", 0) or 0) > 0:
            cmd.extend(["--limit-frames", str(args.limit_frames)])
        return cmd
    if stage == "render":
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "render_project_slideshow_video.py"),
            "--project-json",
            str(project_json),
        ]
        if getattr(args, "render_dry_run", False) or bool(project.get("workflow", {}).get("render_dry_run")):
            cmd.append("--dry-run")
        return cmd
    return command_map[stage]


def post_stage_update(project_json: Path, stage: str) -> None:
    stage = normalize_stage_name(stage)
    project = load_project(project_json)
    if stage == "transcription":
        meta_path = Path(project["transcription"]["meta_json_path"])
        if meta_path.exists():
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
        project["current_stage"] = "author_narration_beats"
    elif stage == "author_narration_beats":
        project["current_stage"] = "build_visual_shot_plan"
    elif stage == "build_visual_shot_plan":
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
    elif stage == "normalize_images":
        project["current_stage"] = "timeline"
    elif stage == "timeline":
        project["current_stage"] = "render"
    elif stage == "render":
        render_status = str(project.get("render", {}).get("status", "")).strip().lower()
        if render_status == "dry_run":
            project["status"] = "in_progress"
            project["current_stage"] = "production_report"
        else:
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


def next_resume_stage(project: dict[str, Any]) -> str:
    for stage in STAGE_SEQUENCE:
        if not stage_done(project, stage):
            return stage
    return STAGE_SEQUENCE[-1]


VALIDATION_MAP = {
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
    "author_narration_beats": "author_narration_beats",
    "build_visual_shot_plan": "build_visual_shot_plan",
    "build_frame_briefs": "build_frame_briefs",
    "attach_reference_assets": "entity_reference_lock",
    "generate_fastgen_prompt_drafts": "generate_fastgen_prompt_drafts",
    "generation_lock": "generation_lock",
    "export_montage_map": "export_montage_map",
    "export_generation_batches": "export_generation_batches",
    "report": "report",
    "motion_plan": "motion_plan",
    "final_review": "final_review",
    "generate_images": "images",
    "image_qc": "image_qc",
    "normalize_images": "normalized_images",
    "timeline": "timeline",
    "render": "render",
}


def run_pipeline(args: argparse.Namespace) -> int:
    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    active_profile = resolve_runtime_profile(active_profile_name(project, getattr(args, "profile", "")))
    resolved_limit_frames = effective_limit_frames(project, getattr(args, "limit_frames", 0), active_profile)
    args.limit_frames = int(resolved_limit_frames or 0)
    state_db_path = resolve_state_db_path(project_json, project, args.state_db or None)
    conn = connect_state_db(state_db_path)
    project_id = str(project.get("project_id", ""))
    requested_to_stage = str(args.to_stage or "")
    try:
        start_stage = normalize_stage_name(args.from_stage) if args.from_stage else (next_resume_stage(project) if args.resume else STAGE_SEQUENCE[0])
        end_stage = normalize_stage_name(args.to_stage)
        selected_stages = STAGE_SEQUENCE[stage_index(start_stage) : stage_index(end_stage) + 1]
        resolve_stale_stages(conn, project_id=project_id, ordered_stage_hashes=stage_hash_snapshot(project_json, project, selected_stages))

        append_log(project, f"Package pipeline run requested: {selected_stages}")
        append_event(project, {"kind": "pipeline_start", "stages": selected_stages, "entrypoint": "yt_nonstop.cli"})

        for stage in selected_stages:
            project = load_project(project_json)
            current_hashes = stage_hash_snapshot(project_json, project, [stage])[0]
            existing_stage_state = get_stage_state(conn, project_id=project_id, stage_name=stage)
            if (
                args.resume
                and existing_stage_state is not None
                and existing_stage_state.status == "completed"
                and existing_stage_state.input_hash == current_hashes["input_hash"]
                and existing_stage_state.output_hash == current_hashes["output_hash"]
                and bool(current_hashes["output_exists"])
            ):
                append_log(project, f"Skipping completed fresh stage during resume: {stage}")
                print(f"SKIP: {stage} (completed and fresh)")
                continue

            apply_runtime_profile(project, args)
            project.setdefault("state", {})["pipeline_state_path"] = str(state_db_path)
            if getattr(args, "profile", ""):
                project.setdefault("runtime", {})["cli_profile"] = args.profile
            project.setdefault("runtime", {})["real_generation"] = bool(getattr(args, "real_generation", False))
            project["runtime"]["limit_frames"] = int(getattr(args, "limit_frames", 0) or 0)
            project["runtime"]["render_dry_run"] = bool(getattr(args, "render_dry_run", False))
            runtime_time_range = _runtime_time_range_from_args(args)
            if runtime_time_range:
                existing_time_range = project.get("runtime", {}).get("time_range", {})
                if isinstance(existing_time_range, dict) and existing_time_range.get("audio_pretrimmed"):
                    runtime_time_range["audio_pretrimmed"] = True
                    for key in ("original_audio_path", "trimmed_audio_path"):
                        if existing_time_range.get(key):
                            runtime_time_range[key] = existing_time_range[key]
                project["runtime"]["time_range"] = runtime_time_range

            if stage == "generate_fastgen_prompt_drafts":
                context_cmd = [sys.executable, str(ROOT / "scripts" / "build_scene_context_pack.py"), "--project-json", str(project_json)]
                append_log(project, f"Building scene context pack: {' '.join(context_cmd)}")
                if args.dry_run:
                    print("DRY-RUN:", " ".join(context_cmd))
                else:
                    subprocess.run(context_cmd, check=True)
                    validate_stage(project_json, "scene_context_pack", args.dry_run)
            if stage == "generate_fastgen_prompt_drafts" and args.auto_author_llm:
                auto_cmd = [sys.executable, str(ROOT / "scripts" / "auto_author_llm_prompts.py"), "--project-json", str(project_json)]
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
            mark_stage_running(conn, project_id=project_id, stage_name=stage, input_hash=current_hashes["input_hash"])

            try:
                if args.dry_run:
                    print("DRY-RUN:", " ".join(cmd))
                else:
                    subprocess.run(cmd, check=True)
                    post_stage_update(project_json, stage)

                validation_stage = VALIDATION_MAP.get(stage)
                if validation_stage:
                    validate_stage(project_json, validation_stage, args.dry_run)

                if requested_to_stage == "production_report" and stage == "image_qc":
                    extra_commands = [
                        [sys.executable, str(ROOT / "scripts" / "build_regeneration_plan.py"), "--project-json", str(project_json)],
                        [sys.executable, str(ROOT / "scripts" / "build_review_package.py"), "--project-json", str(project_json)],
                    ]
                    for extra_cmd in extra_commands:
                        append_log(project, f"Running production-report prerequisite: {' '.join(extra_cmd)}")
                        append_event(project, {"kind": "stage_dispatch", "stage": "production_report_prerequisite", "command": extra_cmd})
                        if args.dry_run:
                            print("DRY-RUN:", " ".join(extra_cmd))
                        else:
                            subprocess.run(extra_cmd, check=True)

                refreshed_project = load_project(project_json)
                output_hash, _ = compute_stage_output_hash(refreshed_project, stage)
                mark_stage_completed(
                    conn,
                    project_id=project_id,
                    stage_name=stage,
                    input_hash=current_hashes["input_hash"],
                    output_hash=output_hash,
                )
                resolve_stale_stages(conn, project_id=project_id, ordered_stage_hashes=stage_hash_snapshot(project_json, refreshed_project, selected_stages))
            except subprocess.CalledProcessError as exc:
                mark_stage_failed(
                    conn,
                    project_id=project_id,
                    stage_name=stage,
                    input_hash=current_hashes["input_hash"],
                    output_hash=current_hashes["output_hash"],
                    error_message=f"returncode={exc.returncode}",
                )
                raise

        project = load_project(project_json)
        if requested_to_stage == "production_report":
            report_cmd = [sys.executable, str(ROOT / "scripts" / "build_production_report.py"), "--project-json", str(project_json)]
            append_log(project, f"Running post-render production report: {' '.join(report_cmd)}")
            append_event(project, {"kind": "stage_dispatch", "stage": "production_report", "command": report_cmd})
            if args.dry_run:
                print("DRY-RUN:", " ".join(report_cmd))
            else:
                subprocess.run(report_cmd, check=True)
            project = load_project(project_json)
        append_event(project, {"kind": "pipeline_end", "status": "success"})
        append_log(project, "Package pipeline run completed successfully")
        save_project(project_json, project)
        return 0
    except subprocess.CalledProcessError as exc:
        project = load_project(project_json)
        project["status"] = "failed"
        append_event(project, {"kind": "pipeline_end", "status": "failed", "returncode": exc.returncode})
        append_log(project, f"Pipeline failed with return code {exc.returncode}")
        save_project(project_json, project)
        raise
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    stage_choices = STAGE_SEQUENCE + ["generate_fastgen_prompts", "scene_context_pack", "production_report"]
    parser.add_argument("--from", dest="from_stage", choices=stage_choices)
    parser.add_argument("--to", dest="to_stage", choices=stage_choices, default="render")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--render-dry-run", action="store_true")
    parser.add_argument("--state-db", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--real-generation", action="store_true")
    parser.add_argument("--limit-frames", type=int, default=0)
    parser.add_argument("--start-sec", type=float, default=None)
    parser.add_argument("--end-sec", type=float, default=None)
    parser.add_argument("--auto-author-llm", dest="auto_author_llm", action="store_true")
    parser.add_argument("--no-auto-author-llm", dest="auto_author_llm", action="store_false")
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
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    raise SystemExit(run_pipeline(args))


if __name__ == "__main__":  # pragma: no cover
    main()
