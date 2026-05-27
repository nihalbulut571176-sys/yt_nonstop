import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from pipeline_contracts import normalize_text_lower, request_spec_from_project
from project_pipeline_utils import load_json, load_project, normalize_stage_name, save_json, save_project


STAGE_CHOICES = [
    "transcription",
    "transcript_quality",
    "ingest_srt",
    "build_scene_map",
    "expand_storyboard",
    "build_continuity_map",
    "allocate_frames",
    "build_frame_briefs",
    "generate_fastgen_prompt_drafts",
    "generation_lock",
    "quality_assurance",
    "export_montage_map",
    "export_generation_batches",
    "report",
    "motion_plan",
    "final_review",
    "images",
    "normalized_images",
    "timeline",
    "render",
    "generate_fastgen_prompts",
    "scene_context_pack",
    "all",
]


def file_must_exist(path_str: str | None, label: str, errors: list[str]) -> Path | None:
    if not path_str:
        errors.append(f"Missing path for {label}")
        return None
    path = Path(path_str)
    if not path.exists():
        errors.append(f"Missing file for {label}: {path}")
        return None
    return path


def dir_must_exist(path_str: str | None, label: str, errors: list[str]) -> Path | None:
    if not path_str:
        errors.append(f"Missing path for {label}")
        return None
    path = Path(path_str)
    if not path.exists():
        errors.append(f"Missing directory for {label}: {path}")
        return None
    return path


def probe_media_duration(path: Path) -> float | None:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def validate_transcription(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    audio_path = file_must_exist(project["inputs"].get("audio_path"), "inputs.audio_path", errors)
    raw_srt_path = file_must_exist(project["transcription"].get("raw_srt_path") or project["transcription"].get("srt_path"), "transcription.raw_srt_path", errors)
    file_must_exist(project["transcription"].get("segments_json_path"), "transcription.segments_json_path", errors)
    meta_path = file_must_exist(project["transcription"].get("meta_json_path"), "transcription.meta_json_path", errors)

    if meta_path:
        meta = load_json(meta_path)
        if float(meta.get("duration", 0) or 0) <= 0:
            errors.append("Transcription meta duration is missing or invalid")
    if raw_srt_path and not raw_srt_path.read_text(encoding="utf-8-sig").strip():
        errors.append("Raw Whisper SRT file is empty")
    if audio_path:
        probed = probe_media_duration(audio_path)
        if probed is None:
            warnings.append("Could not probe audio duration with ffprobe")
        elif probed <= 0:
            errors.append("Audio duration reported by ffprobe is invalid")
    return errors, warnings


def validate_transcript_quality(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    cleaned_path = file_must_exist(project["transcript_cleanup"].get("cleaned_srt_path"), "transcript_cleanup.cleaned_srt_path", errors)
    cleanup_report_path = file_must_exist(project["transcript_cleanup"].get("cleanup_report_path"), "transcript_cleanup.cleanup_report_path", errors)
    if cleaned_path and Path(project["scene_plan"].get("source_srt_path", "")) != cleaned_path:
        warnings.append("scene_plan.source_srt_path does not point to cleaned.srt")
    if cleanup_report_path and cleanup_report_path.exists():
        report = load_json(cleanup_report_path)
        warnings.extend(report.get("warnings", []))
    return errors, list(dict.fromkeys(warnings))


def validate_scene_plan(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    scene_plan_path = file_must_exist(project["scene_plan"].get("scene_plan_path"), "scene_plan.scene_plan_path", errors)
    if not scene_plan_path:
        return errors, warnings
    scene_plan = load_json(scene_plan_path)
    scenes = scene_plan.get("scenes", [])
    if not scenes:
        errors.append("scene_plan contains no scenes")
        return errors, warnings
    previous_end = -1.0
    seen_ids = set()
    for scene in scenes:
        scene_id = scene.get("scene_id")
        if not scene_id:
            errors.append("Scene without scene_id found")
            continue
        if scene_id in seen_ids:
            errors.append(f"Duplicate scene_id found: {scene_id}")
        seen_ids.add(scene_id)
        start = float(scene.get("start", 0) or 0)
        end = float(scene.get("end", 0) or 0)
        duration = float(scene.get("duration", 0) or 0)
        if end <= start:
            errors.append(f"{scene_id} has invalid timing window")
        if abs((end - start) - duration) > 0.05:
            errors.append(f"{scene_id} duration does not match timing window")
        if previous_end > start + 0.02:
            warnings.append(f"{scene_id} overlaps previous scene")
        previous_end = max(previous_end, end)
        if not str(scene.get("voice_text", "")).strip():
            errors.append(f"{scene_id} has empty voice_text")
    return errors, warnings


def validate_ingest_srt(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    scene_map_path = file_must_exist(project["planning"].get("scene_map_path"), "planning.scene_map_path", errors)
    blocks_path = file_must_exist(project["planning"].get("sentence_blocks_json_path"), "planning.sentence_blocks_json_path", errors)
    if not scene_map_path or not blocks_path:
        return errors, warnings
    payload = load_json(scene_map_path)
    blocks = load_json(blocks_path)
    if not payload.get("sentence_blocks"):
        errors.append("scene_map has no sentence_blocks")
    if not isinstance(blocks, list) or not blocks:
        errors.append("sentence_blocks.json is empty or invalid")
    return errors, warnings


def validate_build_scene_map(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    scene_map_path = file_must_exist(project["planning"].get("scene_map_path"), "planning.scene_map_path", errors)
    if not scene_map_path:
        return errors, warnings
    scene_map = load_json(scene_map_path)
    semantic_units = scene_map.get("semantic_units", [])
    if not semantic_units:
        errors.append("scene_map has no semantic_units")
    for item in semantic_units:
        if not str(item.get("semantic_unit_id", "")).strip():
            errors.append("semantic_unit missing semantic_unit_id")
        if not str(item.get("voice_text", "")).strip():
            errors.append(f"{item.get('semantic_unit_id', '<unknown>')} has empty voice_text")
    return errors, warnings


def validate_expand_storyboard(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    storyboard_path = file_must_exist(project["planning"].get("storyboard_path"), "planning.storyboard_path", errors)
    if not storyboard_path:
        return errors, warnings
    payload = load_json(storyboard_path)
    items = payload.get("items", [])
    spec = request_spec_from_project(project)
    if spec.is_sequence and not items:
        errors.append("storyboard is required for sequence workflow")
    for item in items:
        for field in ("storyboard_id", "semantic_unit_id", "visual_role", "shot_function", "source_stage"):
            if not str(item.get(field, "")).strip():
                errors.append(f"Storyboard item missing required field `{field}`")
    return errors, warnings


def validate_build_continuity_map(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    continuity_path = file_must_exist(project["planning"].get("continuity_map_json_path"), "planning.continuity_map_json_path", errors)
    if not continuity_path:
        return errors, warnings
    payload = load_json(continuity_path)
    for field in ("continuity_world", "continuity_rules", "recurring_motifs"):
        if not payload.get(field):
            errors.append(f"continuity map missing `{field}`")
    if not payload.get("scene_entity_map") and not payload.get("segment_entity_map"):
        warnings.append("continuity map has no scene_entity_map or segment_entity_map; fallback continuity may be used")
    return errors, warnings


def validate_build_frame_briefs(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    briefs_path = file_must_exist(project["planning"].get("frame_briefs_json_path"), "planning.frame_briefs_json_path", errors)
    package_path = file_must_exist(project["prompts"].get("prompt_package_path"), "prompts.prompt_package_path", errors)
    storyboard_path = file_must_exist(project["planning"].get("storyboard_path"), "planning.storyboard_path", errors)
    if not briefs_path or not package_path:
        return errors, warnings
    drafts = load_json(briefs_path)
    package = load_json(package_path)
    package_scene_ids = {item["scene_id"] for item in package.get("items", [])}
    draft_scene_ids = set()
    required_fields = ["frame_id", "scene_id", "storyboard_id", "shot_id", "semantic_unit_id", "visual_role", "shot_function", "frame_brief_hash"]
    if not isinstance(drafts, list) or not drafts:
        errors.append("frame_briefs is empty or not a JSON array")
        return errors, warnings
    for record in drafts:
        frame_id = str(record.get("frame_id", "")).strip()
        if not frame_id:
            errors.append("frame_briefs record missing frame_id")
            continue
        scene_id = str(record.get("scene_id", "")).strip()
        draft_scene_ids.add(scene_id)
        for field in required_fields:
            if not str(record.get(field, "")).strip():
                errors.append(f"{frame_id} missing required field `{field}`")
    if not storyboard_path and request_spec_from_project(project).is_sequence and not request_spec_from_project(project).skip_storyboard_allowed:
        errors.append("Sequence workflow cannot build frame briefs without storyboard")
    if draft_scene_ids != package_scene_ids:
        errors.append("frame_briefs scene coverage does not match prompt_package")
    return errors, warnings


def validate_scene_context_pack(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    context_path = file_must_exist(project["prompts"].get("scene_context_pack_path"), "prompts.scene_context_pack_path", errors)
    if not context_path:
        return errors, warnings
    payload = load_json(context_path)
    if not isinstance(payload, list) or not payload:
        errors.append("scene_context_pack is empty or not a JSON array")
    if request_spec_from_project(project).is_sequence and any(item.get("continuity_fallback_used") for item in payload):
        warnings.append("continuity fallback mode active for one or more context records")
    return errors, warnings


def validate_generate_fastgen_prompt_drafts(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    drafts_path = file_must_exist(project["prompts"].get("llm_prompt_drafts_path"), "prompts.llm_prompt_drafts_path", errors)
    final_scene_plan_path = file_must_exist(project["prompts"].get("final_scene_plan_path"), "prompts.final_scene_plan_path", errors)
    if not drafts_path or not final_scene_plan_path:
        return errors, warnings
    drafts = load_json(drafts_path)
    if not isinstance(drafts, list) or not drafts:
        errors.append("llm_prompt_drafts is empty or not a JSON array")
    for record in drafts:
        for field in ("scene_id", "visual_goal", "final_prompt"):
            if not str(record.get(field, "")).strip():
                errors.append(f"{record.get('scene_id', '<unknown>')} missing required field `{field}`")
        if record.get("active_entity_ids") and not record.get("continuity_cast"):
            warnings.append(f"{record.get('scene_id', '<unknown>')} has active entities but no continuity_cast")
    return errors, warnings


def validate_generation_lock(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    json_path = file_must_exist(project["prompts"].get("generation_locked_json_path"), "prompts.generation_locked_json_path", errors)
    if not json_path:
        return errors, warnings
    rows = load_json(json_path)
    if not isinstance(rows, list) or not rows:
        errors.append("generation_locked_frames is empty or invalid")
        return errors, warnings
    strict = bool(project["workflow"].get("strict_generation_lock"))
    for row in rows:
        status = row.get("generation_lock_status")
        if status == "failed":
            errors.append(f"{row.get('frame_id', '<unknown>')} failed generation lock")
        elif strict and status != "locked":
            errors.append(f"{row.get('frame_id', '<unknown>')} is not fully locked under strict mode")
        elif status == "locked_with_warnings":
            warnings.append(f"{row.get('frame_id', '<unknown>')} locked with warnings: {', '.join(row.get('validation_flags', []))}")
        for field in ("image_prompt", "negative_prompt", "motion_prompt", "continuity_note", "frame_brief_hash"):
            if not str(row.get(field, "")).strip():
                errors.append(f"{row.get('frame_id', '<unknown>')} missing generation lock field `{field}`")
    return errors, warnings


def validate_quality_assurance(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    briefs_path = file_must_exist(project["planning"].get("frame_briefs_json_path"), "planning.frame_briefs_json_path", errors)
    locked_path = file_must_exist(project["prompts"].get("generation_locked_json_path"), "prompts.generation_locked_json_path", errors)
    if not briefs_path or not locked_path:
        return errors, warnings
    frame_briefs = load_json(briefs_path)
    locked_rows = load_json(locked_path)
    if len(frame_briefs) != len(locked_rows):
        errors.append("frame_briefs and generation_locked_frames length mismatch")
    continuity_path_value = project.get("planning", {}).get("continuity_map_json_path")
    continuity_path = Path(continuity_path_value) if continuity_path_value else None
    if request_spec_from_project(project).is_sequence and (continuity_path is None or not continuity_path.exists()):
        warnings.append("continuity_break: continuity map missing, fallback mode in effect")

    previous_end = None
    seen_frame_ids = set()
    scene_windows: dict[str, list[dict[str, Any]]] = {}
    prompt_signatures: dict[str, int] = {}
    for brief in frame_briefs:
        frame_id = brief.get("frame_id")
        if frame_id in seen_frame_ids:
            errors.append(f"Duplicate frame_id found: {frame_id}")
        seen_frame_ids.add(frame_id)
        start = float(brief.get("timeline_in", 0) or 0)
        end = float(brief.get("timeline_out", 0) or 0)
        if end <= start:
            errors.append(f"{frame_id} has invalid timing window")
        if previous_end is not None:
            if start > previous_end + 0.05:
                warnings.append(f"timing_gap: {frame_id} starts after a gap")
            if start < previous_end - 0.02:
                errors.append(f"timing_overlap: {frame_id} overlaps previous frame")
        previous_end = end
        if len({brief.get("scale"), brief.get("angle"), brief.get("scene_type"), brief.get("lighting"), brief.get("visual_density"), brief.get("motion_treatment")}) < 4:
            warnings.append(f"prompt_noise: {frame_id} has low style diversity metadata")
        scene_windows.setdefault(brief["scene_id"], []).append(brief)

    previous = None
    for brief in frame_briefs:
        if previous:
            diff_count = sum(
                1
                for key in ("scale", "angle", "scene_type", "lighting", "emotional_energy", "visual_density", "motion_treatment")
                if previous.get(key) != brief.get(key)
            )
            if diff_count < 2:
                errors.append(f"neighbor_duplicate: {brief['frame_id']} differs from previous frame on fewer than 2 dimensions")
        previous = brief

    for scene_id, window in scene_windows.items():
        signatures = {
            (item.get("scale"), item.get("angle"), item.get("scene_type"), item.get("lighting"), item.get("visual_density"))
            for item in window
        }
        if len(signatures) <= 2 and len(window) >= 3:
            warnings.append(f"scene_monotony: {scene_id} has low variation across its frame window")

    for row in locked_rows:
        signature = normalize_text_lower(row.get("image_prompt", ""))
        prompt_signatures[signature] = prompt_signatures.get(signature, 0) + 1
    duplicates = [signature for signature, count in prompt_signatures.items() if signature and count >= 3]
    if duplicates:
        warnings.append(f"global_visual_repetition: {len(duplicates)} repeated prompt families detected")
    return errors, warnings


def validate_export_montage_map(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    json_path = file_must_exist(project["exports"].get("montage_timing_map_json_path"), "exports.montage_timing_map_json_path", errors)
    csv_path = file_must_exist(project["exports"].get("montage_timing_map_csv_path"), "exports.montage_timing_map_csv_path", errors)
    briefs_path = file_must_exist(project["planning"].get("frame_briefs_json_path"), "planning.frame_briefs_json_path", errors)
    if not json_path or not csv_path or not briefs_path:
        return errors, warnings
    rows = load_json(json_path)
    frame_briefs = load_json(briefs_path)
    if len(rows) != len(frame_briefs):
        errors.append("montage_timing_map does not match frame_brief count")
    return errors, warnings


def validate_export_generation_batches(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    export_path = file_must_exist(project["prompts"].get("fastgen_export_path"), "prompts.fastgen_export_path", errors)
    locked_path = file_must_exist(project["prompts"].get("generation_locked_json_path"), "prompts.generation_locked_json_path", errors)
    if not export_path or not locked_path:
        return errors, warnings
    locked_rows = load_json(locked_path)
    blocks = [block.strip() for block in export_path.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    allowed = {"locked"} if project["workflow"].get("strict_generation_lock") else {"locked", "locked_with_warnings"}
    expected = sum(1 for row in locked_rows if row.get("generation_lock_status") in allowed)
    if len(blocks) != expected:
        errors.append(f"Generator-ready block count mismatch: {len(blocks)} blocks vs {expected} locked frames")
    return errors, warnings


def validate_report(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    report_path = file_must_exist(project["logs"].get("workflow_report_json_path"), "logs.workflow_report_json_path", errors)
    if not report_path:
        return errors, warnings
    payload = load_json(report_path)
    if int(payload.get("frame_brief_count", 0) or 0) <= 0:
        errors.append("workflow report has invalid frame_brief_count")
    if not str(payload.get("generator_ready_path", "")).strip():
        errors.append("workflow report missing generator_ready_path")
    return errors, warnings


def validate_motion_plan(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    json_path = file_must_exist(project["motion"].get("motion_plan_json_path"), "motion.motion_plan_json_path", errors)
    csv_path = file_must_exist(project["motion"].get("motion_plan_csv_path"), "motion.motion_plan_csv_path", errors)
    if not json_path or not csv_path:
        return errors, warnings
    payload = load_json(json_path)
    if not isinstance(payload, list) or not payload:
        errors.append("motion_plan.json is empty or not an array")
    return errors, warnings


def validate_final_review(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    report_path = file_must_exist(project["logs"].get("final_review_report_path"), "logs.final_review_report_path", errors)
    if not report_path:
        return errors, warnings
    payload = load_json(report_path)
    if payload.get("status") == "requires_rework":
        errors.append("final_review marked the package as requires_rework")
    warnings.extend(payload.get("weak_segments", []))
    return errors, warnings


def validate_images(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = file_must_exist(project["images"].get("run_manifest_path"), "images.run_manifest_path", errors)
    raw_dir = dir_must_exist(project["images"].get("raw_images_dir"), "images.raw_images_dir", errors)
    if not manifest_path or not raw_dir:
        return errors, warnings
    manifest = load_json(manifest_path)
    records = manifest.get("generated_images", []) if isinstance(manifest, dict) else manifest
    if not records:
        errors.append("Image manifest contains no generated image records")
        return errors, warnings
    missing_assets = [record.get("scene_id", "<unknown>") for record in records if not record.get("image_path") or not Path(record["image_path"]).exists()]
    if missing_assets:
        errors.append(f"Missing generated image file for {len(missing_assets)} scenes")
    if int(manifest.get("failed_count", 0) or 0) > 0:
        warnings.append(f"Image generation recorded {manifest['failed_count']} failed scenes")
    return errors, warnings


def validate_normalized_images(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    normalized_dir = dir_must_exist(project["images"].get("normalized_images_dir"), "images.normalized_images_dir", errors)
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    scene_plan_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    if not normalized_dir:
        return errors, warnings
    scene_plan = load_json(scene_plan_path)
    missing_assets = []
    for scene in scene_plan.get("scenes", []):
        asset_path = scene.get("render_asset_path") or scene.get("still_image_path")
        if not asset_path or not Path(asset_path).exists():
            missing_assets.append(scene.get("scene_id", "<unknown>"))
    if missing_assets:
        errors.append(f"Missing normalized render assets for {len(missing_assets)} scenes")
    return errors, warnings


def validate_timeline(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ffconcat_path = file_must_exist(project["render"].get("ffconcat_path"), "render.ffconcat_path", errors)
    timeline_path = file_must_exist(project["render"].get("slideshow_timeline_path"), "render.slideshow_timeline_path", errors)
    if not ffconcat_path or not timeline_path:
        return errors, warnings
    timeline = load_json(timeline_path)
    total_duration = sum(float(item.get("duration", 0) or 0) for item in timeline)
    audio_duration = float(project["inputs"].get("audio_duration_seconds") or 0)
    if audio_duration > 0 and abs(total_duration - audio_duration) > 1.0:
        warnings.append(f"Timeline duration differs from audio by {abs(total_duration - audio_duration):.3f}s")
    if "ffconcat version 1.0" not in ffconcat_path.read_text(encoding="utf-8"):
        errors.append("ffconcat header is missing")
    return errors, warnings


def validate_render(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    final_video_path = file_must_exist(project["render"].get("final_video_path"), "render.final_video_path", errors)
    if not final_video_path:
        return errors, warnings
    duration = probe_media_duration(final_video_path)
    audio_duration = float(project["inputs"].get("audio_duration_seconds") or 0)
    if duration is None:
        warnings.append("Could not probe final video duration with ffprobe")
    elif duration <= 0:
        errors.append("Final video duration is invalid")
    elif audio_duration > 0 and abs(duration - audio_duration) > 1.5:
        warnings.append(f"Final video duration differs from audio by {abs(duration - audio_duration):.3f}s")
    if final_video_path.stat().st_size < 1024 * 1024:
        errors.append("Final video is suspiciously small")
    return errors, warnings


VALIDATORS = {
    "transcription": validate_transcription,
    "transcript_quality": validate_transcript_quality,
    "ingest_srt": validate_ingest_srt,
    "build_scene_map": validate_build_scene_map,
    "expand_storyboard": validate_expand_storyboard,
    "build_continuity_map": validate_build_continuity_map,
    "allocate_frames": validate_scene_plan,
    "build_frame_briefs": validate_build_frame_briefs,
    "scene_context_pack": validate_scene_context_pack,
    "generate_fastgen_prompt_drafts": validate_generate_fastgen_prompt_drafts,
    "generate_fastgen_prompts": validate_generate_fastgen_prompt_drafts,
    "generation_lock": validate_generation_lock,
    "quality_assurance": validate_quality_assurance,
    "export_montage_map": validate_export_montage_map,
    "export_generation_batches": validate_export_generation_batches,
    "report": validate_report,
    "motion_plan": validate_motion_plan,
    "final_review": validate_final_review,
    "images": validate_images,
    "normalized_images": validate_normalized_images,
    "timeline": validate_timeline,
    "render": validate_render,
}


def write_report(project_json: Path, project: dict[str, Any], payload: dict[str, Any]) -> None:
    report_path = Path(project["logs"]["qa_report_json_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(report_path, payload)
    project["qc"]["status"] = payload["status"]
    project["qc"]["last_result"] = payload
    save_project(project_json, project)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--stage", default="all", choices=STAGE_CHOICES)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    stages = list(VALIDATORS.keys()) if args.stage == "all" else [normalize_stage_name(args.stage)]
    stage_results = []
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for stage in stages:
        errors, warnings = VALIDATORS[stage](project)
        stage_results.append({"stage": stage, "status": "failed" if errors else "passed", "errors": errors, "warnings": warnings})
        all_errors.extend(f"[{stage}] {message}" for message in errors)
        all_warnings.extend(f"[{stage}] {message}" for message in warnings)

    status = "failed" if all_errors else "passed"
    report = {
        "project_id": project["project_id"],
        "stage": args.stage,
        "status": status,
        "errors": all_errors,
        "warnings": all_warnings,
        "stage_results": stage_results,
    }
    write_report(project_json, project, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if all_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
