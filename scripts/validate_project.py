import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from llm_pipeline_contracts import (
    validate_generation_manifest,
    validate_scene_prompt_drafts_payload,
    validate_visual_bible_payload,
)
from pipeline_contracts import (
    contains_forbidden_terms,
    count_pattern_breaks,
    has_cyrillic,
    normalize_text_lower,
    prompt_length_ok,
    request_spec_from_project,
    similarity_score,
)
from prompt_safety import is_probably_abstract, lint_prompt_observability
from project_pipeline_utils import load_json, load_project, normalize_stage_name, save_json, save_project


STAGE_CHOICES = [
    "transcription",
    "transcript_quality",
    "ingest_srt",
    "build_scene_map",
    "expand_storyboard",
    "build_reference_prompt_pack",
    "generate_reference_images",
    "build_subject_registry",
    "build_continuity_map",
    "allocate_frames",
    "build_narration_beats",
    "author_narration_beats",
    "build_visual_shot_plan",
    "build_frame_briefs",
    "attach_reference_assets",
    "generate_fastgen_prompt_drafts",
    "generation_lock",
    "quality_assurance",
    "export_montage_map",
    "export_generation_batches",
    "report",
    "motion_plan",
    "final_review",
    "images",
    "image_qc",
    "normalized_images",
    "timeline",
    "render",
    "entity_reference_lock",
    "generate_fastgen_prompts",
    "scene_context_pack",
    "parse_srt",
    "build_scenes",
    "build_subscenes",
    "build_storyboard",
    "directors_cut",
    "write_prompts",
    "qc",
    "rewrite_flagged",
    "export_generator_queue",
    "export_edit_timeline",
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


def _parse_dot_timestamp(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(".")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


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


def validate_parse_srt(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = file_must_exist(project["planning"].get("v2_project_skeleton_path"), "planning.v2_project_skeleton_path", errors)
    if not path:
        return errors, warnings
    payload = load_json(path)
    if not isinstance(payload.get("sentence_blocks"), list) or not payload.get("sentence_blocks"):
        errors.append("canonical_project.json has no sentence_blocks")
    return errors, warnings


def validate_build_scenes(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = file_must_exist(project["planning"].get("global_scene_plan_path"), "planning.global_scene_plan_path", errors)
    if not path:
        return errors, warnings
    payload = load_json(path)
    scenes = payload.get("scenes", [])
    if not scenes:
        errors.append("global_scene_plan has no scenes")
        return errors, warnings
    seen_ids = set()
    previous_end = -1.0
    for scene in scenes:
        scene_id = str(scene.get("scene_id", "")).strip()
        if not scene_id:
            errors.append("global scene missing scene_id")
            continue
        if scene_id in seen_ids:
            errors.append(f"duplicate global scene_id: {scene_id}")
        seen_ids.add(scene_id)
        start = float(scene.get("start", 0) or 0)
        end = float(scene.get("end", 0) or 0)
        if end <= start:
            errors.append(f"{scene_id} has invalid timing")
        if previous_end > start + 0.02:
            errors.append(f"{scene_id} overlaps previous global scene")
        previous_end = end
        if int(scene.get("target_frame_count", 0) or 0) <= 0:
            errors.append(f"{scene_id} has invalid target_frame_count")
    return errors, warnings


def validate_build_subscenes(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = file_must_exist(project["planning"].get("subscene_plan_path"), "planning.subscene_plan_path", errors)
    global_path = file_must_exist(project["planning"].get("global_scene_plan_path"), "planning.global_scene_plan_path", errors)
    if not path or not global_path:
        return errors, warnings
    payload = load_json(path)
    subscenes = payload.get("subscenes", [])
    if not subscenes:
        errors.append("subscene_plan has no subscenes")
        return errors, warnings
    parent_scene_ids = {scene["scene_id"] for scene in load_json(global_path).get("scenes", [])}
    seen_ids = set()
    for subscene in subscenes:
        subscene_id = str(subscene.get("subscene_id", "")).strip()
        if not subscene_id:
            errors.append("subscene missing subscene_id")
            continue
        if subscene_id in seen_ids:
            errors.append(f"duplicate subscene_id: {subscene_id}")
        seen_ids.add(subscene_id)
        if subscene.get("scene_id") not in parent_scene_ids:
            errors.append(f"{subscene_id} points to unknown global scene")
        for field in ("function", "visual_conflict", "transition_to_next"):
            if not str(subscene.get(field, "")).strip():
                errors.append(f"{subscene_id} missing `{field}`")
    return errors, warnings


def validate_build_storyboard(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = file_must_exist(project["planning"].get("storyboard_frames_path"), "planning.storyboard_frames_path", errors)
    scene_plan_path = file_must_exist(project["scene_plan"].get("scene_plan_path"), "scene_plan.scene_plan_path", errors)
    if not path or not scene_plan_path:
        return errors, warnings
    frames = load_json(path).get("frames", [])
    scenes = load_json(scene_plan_path).get("scenes", [])
    if len(frames) != len(scenes):
        errors.append("storyboard_frames count does not match canonical scene_plan count")
    canonical = {
        item["scene_id"]: (float(item["start"]), float(item["end"]), float(item["duration"]))
        for item in scenes
    }
    seen_ids = set()
    for frame in frames:
        frame_id = str(frame.get("frame_id", "")).strip()
        if not frame_id:
            errors.append("storyboard frame missing frame_id")
            continue
        if frame_id in seen_ids:
            errors.append(f"duplicate frame_id: {frame_id}")
        seen_ids.add(frame_id)
        scene_id = frame.get("scene_id")
        if scene_id not in canonical:
            errors.append(f"{frame_id} points to unknown scene_id")
            continue
        start, end, duration = canonical[scene_id]
        if abs(_parse_dot_timestamp(frame.get("start_time", "00:00:00.000")) - start) > 0.05:
            errors.append(f"{frame_id} changed canonical start timing")
        if abs(_parse_dot_timestamp(frame.get("end_time", "00:00:00.000")) - end) > 0.05:
            errors.append(f"{frame_id} changed canonical end timing")
        if abs(float(frame.get("duration_sec", 0) or 0) - duration) > 0.05:
            errors.append(f"{frame_id} changed canonical duration")
        for field in ("subscene_id", "mini_world", "why_this_frame_exists"):
            if not str(frame.get(field, "")).strip():
                errors.append(f"{frame_id} missing `{field}`")
    return errors, warnings


def validate_directors_cut(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    review_path = file_must_exist(project["prompts"].get("directors_cut_review_path"), "prompts.directors_cut_review_path", errors)
    storyboard_path = file_must_exist(project["planning"].get("storyboard_frames_path"), "planning.storyboard_frames_path", errors)
    if not review_path or not storyboard_path:
        return errors, warnings
    review_frames = load_json(review_path).get("frames", [])
    storyboard_frames = load_json(storyboard_path).get("frames", [])
    if len(review_frames) != len(storyboard_frames):
        errors.append("directors_cut review count does not match storyboard frame count")
    valid_statuses = {"approved", "rewrite", "revised", "pending"}
    for record in review_frames:
        if record.get("dc_status") not in valid_statuses:
            errors.append(f"{record.get('frame_id', '<unknown>')} has invalid dc_status")
    return errors, warnings


def validate_write_prompts(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    storyboard_path = file_must_exist(project["planning"].get("storyboard_frames_path"), "planning.storyboard_frames_path", errors)
    prompt_package_path = file_must_exist(project["prompts"].get("prompt_package_path"), "prompts.prompt_package_path", errors)
    final_scene_plan_path = file_must_exist(project["prompts"].get("final_scene_plan_path"), "prompts.final_scene_plan_path", errors)
    if not storyboard_path or not prompt_package_path or not final_scene_plan_path:
        return errors, warnings
    frames = load_json(storyboard_path).get("frames", [])
    items = load_json(prompt_package_path).get("items", [])
    if len(items) != len(frames):
        errors.append("prompt_package item count does not match storyboard frame count")
    for frame in frames:
        frame_id = frame.get("frame_id", "<unknown>")
        prompt = str(frame.get("image_prompt_final", "")).strip()
        if not prompt:
            errors.append(f"{frame_id} missing image_prompt_final")
            continue
        if has_cyrillic(prompt):
            errors.append(f"{frame_id} contains Cyrillic in image_prompt_final")
        if not prompt_length_ok(prompt):
            errors.append(f"{frame_id} exceeds prompt length limit")
        forbidden = contains_forbidden_terms(prompt)
        if forbidden:
            warnings.append(f"{frame_id} contains forbidden terms: {', '.join(forbidden)}")
        if not str(frame.get("negative_prompt", "")).strip():
            errors.append(f"{frame_id} missing negative_prompt")
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


def validate_build_reference_prompt_pack(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    pack_path = file_must_exist(project["prompts"].get("reference_prompt_pack_path"), "prompts.reference_prompt_pack_path", errors)
    if not pack_path:
        return errors, warnings
    payload = load_json(pack_path)
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        errors.append("reference_prompt_pack has no items")
        return errors, warnings
    seen_ids = set()
    for item in items:
        asset_id = str(item.get("reference_asset_id", "")).strip()
        if not asset_id:
            errors.append("reference prompt item missing reference_asset_id")
            continue
        if asset_id in seen_ids:
            errors.append(f"duplicate reference_asset_id: {asset_id}")
        seen_ids.add(asset_id)
        if has_cyrillic(str(item.get("prompt", ""))):
            errors.append(f"{asset_id} contains Cyrillic in reference prompt")
        if not str(item.get("output_path", "")).strip():
            errors.append(f"{asset_id} missing output_path")
    return errors, warnings


def validate_generate_reference_images(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = file_must_exist(
        project["prompts"].get("reference_generation_manifest_path"),
        "prompts.reference_generation_manifest_path",
        errors,
    )
    pack_path = file_must_exist(project["prompts"].get("reference_prompt_pack_path"), "prompts.reference_prompt_pack_path", errors)
    if not manifest_path or not pack_path:
        return errors, warnings
    manifest = load_json(manifest_path)
    items = manifest.get("items", [])
    if not isinstance(items, list):
        errors.append("reference_generation_manifest items must be a list")
        return errors, warnings
    failed = [item for item in items if item.get("status") == "failed"]
    if failed:
        warnings.append(f"reference generation failures present: {len(failed)}")
    for item in items:
        status = str(item.get("status", "")).strip()
        if status in {"generated", "existing"}:
            output_path = item.get("output_path")
            if not output_path or not Path(output_path).exists():
                errors.append(f"missing generated reference output: {output_path}")
    return errors, warnings


def validate_build_subject_registry(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    registry_path = file_must_exist(project["prompts"].get("subject_registry_path"), "prompts.subject_registry_path", errors)
    assets_path = file_must_exist(project["prompts"].get("reference_assets_manifest_path"), "prompts.reference_assets_manifest_path", errors)
    mapping_path = file_must_exist(project["prompts"].get("reference_mapping_path"), "prompts.reference_mapping_path", errors)
    if not registry_path or not assets_path or not mapping_path:
        return errors, warnings
    registry = load_json(registry_path)
    assets = load_json(assets_path)
    subjects = registry.get("subjects", [])
    if not isinstance(subjects, list):
        errors.append("subject_registry subjects must be a list")
        return errors, warnings
    subject_ids = set()
    for subject in subjects:
        subject_id = str(subject.get("subject_id", "")).strip()
        if not subject_id:
            errors.append("subject profile missing subject_id")
            continue
        if subject_id in subject_ids:
            errors.append(f"duplicate subject_id: {subject_id}")
        subject_ids.add(subject_id)
    for asset in assets.get("reference_assets", []):
        if asset.get("subject_id") not in subject_ids:
            errors.append(f"reference asset points to unknown subject_id: {asset.get('subject_id')}")
    mapping = load_json(mapping_path)
    for asset in assets.get("reference_assets", []):
        asset_id = asset.get("reference_asset_id")
        if asset_id and asset_id not in mapping:
            errors.append(f"reference mapping missing asset id: {asset_id}")
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
    narration_beats_path = file_must_exist(project["planning"].get("narration_beats_path"), "planning.narration_beats_path", errors)
    visual_shot_plan_path = file_must_exist(project["prompts"].get("visual_shot_plan_path"), "prompts.visual_shot_plan_path", errors)
    if not briefs_path or not package_path:
        return errors, warnings
    drafts = load_json(briefs_path)
    package = load_json(package_path)
    package_scene_ids = {item["scene_id"] for item in package.get("items", [])}
    beats_by_scene = {}
    if narration_beats_path:
        beats_by_scene = {
            item.get("scene_id"): item
            for item in load_json(narration_beats_path).get("beats", [])
            if item.get("scene_id")
        }
    scene_to_shot = {}
    shots_by_id = {}
    if visual_shot_plan_path:
        shot_plan = load_json(visual_shot_plan_path)
        scene_to_shot = shot_plan.get("scene_to_shot", {})
        shots_by_id = {item["shot_id"]: item for item in shot_plan.get("shots", []) if item.get("shot_id")}
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
        if record.get("subject_visible") and not record.get("primary_subject_id"):
            errors.append(f"{frame_id} subject_visible but no primary_subject_id")
        if not str(record.get("beat_id", "")).strip():
            errors.append(f"{frame_id} missing required field `beat_id`")
        if not str(record.get("visualized_claim", "")).strip():
            errors.append(f"{frame_id} missing required field `visualized_claim`")
        must_show = record.get("must_show", [])
        if not isinstance(must_show, list) or not [item for item in must_show if str(item).strip()]:
            errors.append(f"{frame_id} must contain at least one `must_show` item")
        if record.get("entity_locks") is not None and not isinstance(record.get("entity_locks"), list):
            errors.append(f"{frame_id} entity_locks must be a list")
        for field in ("generation_mode", "shot_type", "transition_in", "transition_out", "beat_priority"):
            if not str(record.get(field, "")).strip():
                errors.append(f"{frame_id} missing required field `{field}`")
        beat = beats_by_scene.get(scene_id)
        if beat and record.get("beat_id") != beat.get("beat_id"):
            errors.append(f"{frame_id} beat_id does not match narration_beats for {scene_id}")
        mapping = scene_to_shot.get(scene_id, {})
        shot_id = str(record.get("shot_id", "")).strip()
        if mapping and shot_id != mapping.get("shot_id"):
            errors.append(f"{frame_id} shot_id does not match visual_shot_plan for {scene_id}")
        shot = shots_by_id.get(shot_id, {})
        if shot and str(record.get("film_block_id", "")).strip() != str(shot.get("film_block_id", "")).strip():
            errors.append(f"{frame_id} film_block_id does not match visual_shot_plan for {scene_id}")
        if beat and not str(record.get("voice_text", "")).strip():
            warnings.append(f"{frame_id} missing voice_text even though narration beat is available")
    if not storyboard_path and request_spec_from_project(project).is_sequence and not request_spec_from_project(project).skip_storyboard_allowed:
        errors.append("Sequence workflow cannot build frame briefs without storyboard")
    if draft_scene_ids != package_scene_ids:
        errors.append("frame_briefs scene coverage does not match prompt_package")
    return errors, warnings


def validate_build_narration_beats(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    beats_path = file_must_exist(project["planning"].get("narration_beats_path"), "planning.narration_beats_path", errors)
    scene_plan_path = file_must_exist(project["scene_plan"].get("scene_plan_path"), "scene_plan.scene_plan_path", errors)
    if not beats_path or not scene_plan_path:
        return errors, warnings
    payload = load_json(beats_path)
    scene_plan = load_json(scene_plan_path)
    beats = payload.get("beats", [])
    scenes = scene_plan.get("scenes", [])
    if not isinstance(beats, list) or not beats:
        errors.append("narration_beats payload has no beats")
        return errors, warnings
    if len(beats) != len(scenes):
        errors.append("narration_beats count does not match scene_plan scene count")
    scene_index = {scene.get("scene_id"): scene for scene in scenes if scene.get("scene_id")}
    previous_end = -1.0
    for index, beat in enumerate(beats, start=1):
        beat_id = str(beat.get("beat_id", "")).strip()
        scene_id = str(beat.get("scene_id", "")).strip()
        if not beat_id:
            errors.append(f"beat #{index} missing beat_id")
            continue
        if not scene_id:
            errors.append(f"{beat_id} missing scene_id")
            continue
        scene = scene_index.get(scene_id)
        if not scene:
            errors.append(f"{beat_id} points to unknown scene_id {scene_id}")
            continue
        start = float(beat.get("start", 0) or 0)
        end = float(beat.get("end", 0) or 0)
        duration = float(beat.get("duration", 0) or 0)
        if abs(start - float(scene.get("start", 0) or 0)) > 0.02:
            errors.append(f"{beat_id} start does not match scene timing")
        if abs(end - float(scene.get("end", 0) or 0)) > 0.02:
            errors.append(f"{beat_id} end does not match scene timing")
        if abs(duration - float(scene.get("duration", 0) or 0)) > 0.02:
            errors.append(f"{beat_id} duration does not match scene timing")
        if previous_end > start + 0.02:
            errors.append(f"{beat_id} overlaps previous beat")
        previous_end = max(previous_end, end)
        if not str(beat.get("voice_text", "")).strip():
            errors.append(f"{beat_id} missing voice_text")
        must_visualize = beat.get("must_visualize", [])
        if not isinstance(must_visualize, list) or not [item for item in must_visualize if str(item).strip()]:
            errors.append(f"{beat_id} must contain at least one must_visualize item")
    return errors, warnings


def validate_author_narration_beats(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    abstract_only_terms = {"betrayal", "danger", "truth", "corruption", "systemic failure", "identity", "logic", "network", "pressure"}
    errors, warnings = validate_build_narration_beats(project)
    if errors:
        return errors, warnings
    beats_path = Path(project["planning"]["narration_beats_path"])
    beats = load_json(beats_path).get("beats", [])
    for beat in beats:
        beat_id = beat.get("beat_id", "<unknown>")
        if not str(beat.get("spoken_claim", "")).strip():
            errors.append(f"{beat_id} missing spoken_claim")
        must_visualize = beat.get("must_visualize", [])
        if not isinstance(must_visualize, list) or not must_visualize:
            errors.append(f"{beat_id} missing must_visualize")
            continue
        drawable = False
        for item in must_visualize:
            cleaned = normalize_text_lower(str(item))
            if not cleaned:
                continue
            if cleaned in abstract_only_terms or is_probably_abstract(cleaned):
                errors.append(f"{beat_id} contains abstract-only must_visualize item: {item}")
                continue
            warnings_for_item = lint_prompt_observability(cleaned, what_is_in_frame=cleaned)
            if len(warnings_for_item) < 3:
                drawable = True
        if not drawable:
            errors.append(f"{beat_id} has no clearly drawable must_visualize item")
    return errors, warnings


def validate_build_visual_shot_plan(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    shot_plan_path = file_must_exist(project["prompts"].get("visual_shot_plan_path"), "prompts.visual_shot_plan_path", errors)
    beats_path = file_must_exist(project["planning"].get("narration_beats_path"), "planning.narration_beats_path", errors)
    if not shot_plan_path or not beats_path:
        return errors, warnings
    shot_plan = load_json(shot_plan_path)
    beats = load_json(beats_path).get("beats", [])
    shots = shot_plan.get("shots", [])
    scene_to_shot = shot_plan.get("scene_to_shot", {})
    if not shots:
        errors.append("visual_shot_plan has no shots")
        return errors, warnings
    beat_scene_ids = {beat.get("scene_id") for beat in beats if beat.get("scene_id")}
    for scene_id in beat_scene_ids:
        mapping = scene_to_shot.get(scene_id)
        if not mapping:
            errors.append(f"visual_shot_plan missing scene_to_shot mapping for {scene_id}")
            continue
        if not str(mapping.get("shot_id", "")).strip():
            errors.append(f"visual_shot_plan mapping for {scene_id} missing shot_id")
    for shot in shots:
        shot_id = shot.get("shot_id", "<unknown>")
        for field in ("film_block_id", "generation_mode", "shot_type", "visual_function", "camera", "lighting", "transition_in", "transition_out"):
            if not str(shot.get(field, "")).strip():
                errors.append(f"{shot_id} missing visual_shot_plan field `{field}`")
        if not isinstance(shot.get("must_show", []), list) or not [item for item in shot.get("must_show", []) if str(item).strip()]:
            errors.append(f"{shot_id} missing must_show coverage")
    return errors, warnings


def validate_attach_reference_assets(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    briefs_path = file_must_exist(project["planning"].get("frame_briefs_json_path"), "planning.frame_briefs_json_path", errors)
    report_path = file_must_exist(project["planning"].get("reference_binding_report_path"), "planning.reference_binding_report_path", errors)
    registry_path = file_must_exist(project["prompts"].get("subject_registry_path"), "prompts.subject_registry_path", errors)
    if not briefs_path or not report_path or not registry_path:
        return errors, warnings
    frame_briefs = load_json(briefs_path)
    registry = load_json(registry_path)
    known_subject_ids = {item["subject_id"] for item in registry.get("subjects", [])}
    for frame in frame_briefs:
        frame_id = frame.get("frame_id", "<unknown>")
        visible = bool(frame.get("subject_visible"))
        primary_subject_id = frame.get("primary_subject_id")
        mentioned_subject_ids = frame.get("mentioned_subject_ids", [])
        visible_subject_ids = frame.get("visible_subject_ids", [])
        reference_bindings = frame.get("reference_bindings", [])
        reference_images = frame.get("reference_images", [])
        if primary_subject_id and primary_subject_id not in known_subject_ids:
            errors.append(f"unknown_subject_id: {frame_id}:{primary_subject_id}")
        if visible and not primary_subject_id:
            errors.append(f"subject_visible_but_no_subject_id: {frame_id}")
        if not visible and reference_bindings:
            errors.append(f"reference_attached_without_visible_subject: {frame_id}")
        if frame.get("subject_continuity_strength") == "strict" and not reference_images:
            errors.append(f"strict_subject_without_reference: {frame_id}")
        if len(reference_images) > 3:
            errors.append(f"too_many_references_on_frame: {frame_id}")
        if mentioned_subject_ids and not visible_subject_ids and reference_bindings:
            errors.append(f"subject_mentioned_but_not_marked_visible: {frame_id}")
        for binding in reference_bindings:
            for asset_path in frame.get("reference_images", []):
                if not Path(asset_path).exists():
                    errors.append(f"reference_asset_file_missing: {frame_id}:{asset_path}")
    return errors, warnings


def validate_entity_reference_lock(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors, warnings = validate_attach_reference_assets(project)
    entity_registry_path = file_must_exist(project["prompts"].get("entity_registry_path"), "prompts.entity_registry_path", errors)
    briefs_path = file_must_exist(project["planning"].get("frame_briefs_json_path"), "planning.frame_briefs_json_path", errors)
    if not entity_registry_path or not briefs_path:
        return errors, warnings
    entities = load_json(entity_registry_path).get("entities", [])
    entity_by_id = {item["entity_id"]: item for item in entities if item.get("entity_id")}
    frame_briefs = load_json(briefs_path)
    for frame in frame_briefs:
        frame_id = frame.get("frame_id", "<unknown>")
        visible_ids = frame.get("visible_subject_ids", [])
        reference_ids = frame.get("reference_ids", [])
        for entity_id in visible_ids:
            entity = entity_by_id.get(entity_id)
            if not entity:
                continue
            if entity.get("identity_lock") == "required" or entity.get("reference_policy") == "required":
                if not reference_ids:
                    errors.append(f"missing_required_reference_lock: {frame_id}:{entity_id}")
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
    visual_bible_path = file_must_exist(project["prompts"].get("visual_bible_path"), "prompts.visual_bible_path", errors)
    final_scene_plan_path = file_must_exist(project["prompts"].get("final_scene_plan_path"), "prompts.final_scene_plan_path", errors)
    prompt_package_path = file_must_exist(project["prompts"].get("prompt_package_path"), "prompts.prompt_package_path", errors)
    if not drafts_path or not final_scene_plan_path or not prompt_package_path or not visual_bible_path:
        return errors, warnings
    drafts = load_json(drafts_path)
    prompt_package = load_json(prompt_package_path)
    visual_bible = load_json(visual_bible_path)
    final_scene_plan = load_json(final_scene_plan_path)
    draft_errors, draft_warnings = validate_scene_prompt_drafts_payload(
        drafts,
        expected_scene_ids=[item["scene_id"] for item in prompt_package.get("items", [])],
    )
    bible_errors, bible_warnings = validate_visual_bible_payload(visual_bible)
    errors.extend(draft_errors)
    errors.extend(bible_errors)
    warnings.extend(draft_warnings)
    warnings.extend(bible_warnings)
    package_items = {item["scene_id"]: item for item in prompt_package.get("items", []) if item.get("scene_id")}
    final_scene_by_id = {item["scene_id"]: item for item in final_scene_plan.get("scenes", []) if item.get("scene_id")}
    for draft in drafts if isinstance(drafts, list) else []:
        scene_id = draft.get("scene_id")
        frame_id = str(draft.get("frame_id", "")).strip()
        beat_id = str(draft.get("beat_id", "")).strip()
        if not frame_id:
            errors.append(f"{scene_id or '<unknown>'} missing frame_id")
        if not beat_id:
            errors.append(f"{scene_id or '<unknown>'} missing beat_id")
        if not str(draft.get("visualized_claim", "")).strip():
            errors.append(f"{scene_id or '<unknown>'} missing visualized_claim")
        must_not_show = draft.get("must_not_show")
        if must_not_show is not None and not isinstance(must_not_show, list):
            errors.append(f"{scene_id or '<unknown>'} must_not_show must be a list when present")
        package_item = package_items.get(scene_id, {})
        final_scene = final_scene_by_id.get(scene_id, {})
        expected_beat = package_item.get("beat_id") or final_scene.get("beat_id")
        if expected_beat and beat_id and expected_beat != beat_id:
            errors.append(f"{scene_id} beat_id does not match prompt package/final scene plan")
        visualized_claim = normalize_text_lower(str(draft.get("visualized_claim", "")))
        prompt_blob = normalize_text_lower(" ".join([str(draft.get("final_prompt", "")), str(draft.get("visual_goal", ""))]))
        if visualized_claim and visualized_claim not in prompt_blob:
            warnings.append(f"{scene_id} visualized_claim is not explicitly grounded in final_prompt/visual_goal")
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
        for field in ("image_prompt", "negative_prompt", "motion_prompt", "continuity_note", "frame_brief_hash", "scene_id"):
            if not str(row.get(field, "")).strip():
                errors.append(f"{row.get('frame_id', '<unknown>')} missing generation lock field `{field}`")
        if not str(row.get("beat_id", "")).strip():
            errors.append(f"{row.get('frame_id', '<unknown>')} missing generation lock field `beat_id`")
        if row.get("reference_ids") is not None and not isinstance(row.get("reference_ids"), list):
            errors.append(f"{row.get('frame_id', '<unknown>')} reference_ids must be a list")
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
    locked_by_frame = {row.get("frame_id"): row for row in locked_rows if row.get("frame_id")}
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
        if not str(brief.get("beat_id", "")).strip():
            errors.append(f"{frame_id} missing beat_id")
        if not str(brief.get("visualized_claim", "")).strip():
            errors.append(f"{frame_id} missing visualized_claim")
        must_show = brief.get("must_show", [])
        if not isinstance(must_show, list) or not [item for item in must_show if str(item).strip()]:
            errors.append(f"{frame_id} has empty must_show coverage")
        locked = locked_by_frame.get(frame_id, {})
        prompt_blob = normalize_text_lower(" ".join([str(locked.get("image_prompt", "")), str(locked.get("continuity_note", ""))]))
        claim = normalize_text_lower(str(brief.get("visualized_claim", "")))
        if claim and claim not in prompt_blob:
            warnings.append(f"visualized_claim_not_grounded: {frame_id}")
        if brief.get("entity_locks"):
            required_entities = [
                entity
                for entity in brief.get("entity_locks", [])
                if entity.get("reference_policy") == "required" or entity.get("identity_lock") == "required"
            ]
            if required_entities and not locked.get("reference_ids"):
                errors.append(f"missing_required_reference_lock: {frame_id}")

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


def validate_image_qc(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    qc_path = file_must_exist(project["images"].get("image_qc_report_path"), "images.image_qc_report_path", errors)
    selected_path = file_must_exist(project["images"].get("selected_images_manifest_path"), "images.selected_images_manifest_path", errors)
    if not qc_path or not selected_path:
        return errors, warnings
    qc_payload = load_json(qc_path)
    selected_payload = load_json(selected_path)
    qc_rows = qc_payload.get("images", [])
    selected_rows = selected_payload.get("selected_images", [])
    if not isinstance(qc_rows, list) or not qc_rows:
        errors.append("image_qc_report has no image rows")
        return errors, warnings
    if not isinstance(selected_rows, list) or not selected_rows:
        errors.append("selected_images_manifest has no selected_images rows")
        return errors, warnings
    seen_scenes = set()
    for row in selected_rows:
        scene_id = str(row.get("scene_id", "")).strip()
        if not scene_id:
            errors.append("selected image row missing scene_id")
            continue
        seen_scenes.add(scene_id)
        if not str(row.get("beat_id", "")).strip():
            errors.append(f"{scene_id} selected image missing beat_id")
        if not str(row.get("voice_text", "")).strip():
            errors.append(f"{scene_id} selected image missing voice_text")
        if not str(row.get("visualized_claim", "")).strip():
            errors.append(f"{scene_id} selected image missing visualized_claim")
        if str(row.get("selection_status", "")).strip() not in {"use", "manual_review"}:
            errors.append(f"{scene_id} selected image has invalid selection_status `{row.get('selection_status')}`")
        if row.get("coverage_status") != "pass":
            errors.append(f"{scene_id} selected image failed semantic coverage")
        if row.get("semantic_flags"):
            errors.append(f"{scene_id} selected image has semantic flags: {', '.join(row.get('semantic_flags', []))}")
        image_path = row.get("selected_image_path") or row.get("image_path")
        if not image_path or not Path(image_path).exists():
            errors.append(f"{scene_id} selected image file is missing")
    qc_by_scene = {row.get("scene_id"): row for row in qc_rows if row.get("scene_id")}
    for scene_id in seen_scenes:
        qc_row = qc_by_scene.get(scene_id)
        if not qc_row:
            errors.append(f"{scene_id} missing qc row for selected scene")
    return errors, warnings


def validate_qc(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    storyboard_path = file_must_exist(project["planning"].get("storyboard_frames_path"), "planning.storyboard_frames_path", errors)
    rewrite_path = file_must_exist(project["prompts"].get("rewrite_queue_path"), "prompts.rewrite_queue_path", errors)
    report_path = file_must_exist(project["reports"].get("qc_report_md_path"), "reports.qc_report_md_path", errors)
    duplicates_path = file_must_exist(project["reports"].get("duplicate_report_csv_path"), "reports.duplicate_report_csv_path", errors)
    weak_frames_path = file_must_exist(project["reports"].get("weak_frames_csv_path"), "reports.weak_frames_csv_path", errors)
    if not storyboard_path or not rewrite_path or not report_path or not duplicates_path or not weak_frames_path:
        return errors, warnings
    frames = load_json(storyboard_path).get("frames", [])
    rewrite_items = load_json(rewrite_path).get("frames_to_rewrite", [])
    pattern_breaks = count_pattern_breaks(frames, seconds_window=30.0)
    if len(frames) >= 6 and pattern_breaks <= 0:
        warnings.append("No pattern break detected within 30-second windows")
    for frame in frames:
        frame_id = frame.get("frame_id", "<unknown>")
        prompt = frame.get("image_prompt_final", "")
        if has_cyrillic(prompt):
            errors.append(f"{frame_id} contains Cyrillic in generator prompt")
        if not prompt_length_ok(prompt):
            errors.append(f"{frame_id} exceeds prompt length limit")
        if not str(frame.get("negative_prompt", "")).strip():
            errors.append(f"{frame_id} missing negative_prompt")
    previous = None
    for frame in frames:
        if previous is not None and similarity_score(previous.get("image_prompt_final", ""), frame.get("image_prompt_final", "")) >= 85:
            errors.append(f"possible_duplicate_prompt: {frame.get('frame_id', '<unknown>')}")
        previous = frame
    if not rewrite_items and any(frame.get("dc_status") == "rewrite" for frame in frames):
        errors.append("rewrite_queue missing Director's Cut rewrite targets")
    return errors, warnings


def validate_rewrite_flagged(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    storyboard_path = file_must_exist(project["planning"].get("storyboard_frames_path"), "planning.storyboard_frames_path", errors)
    if not storyboard_path:
        return errors, warnings
    frames = load_json(storyboard_path).get("frames", [])
    for frame in frames:
        if frame.get("dc_status") == "revised" and "possible_duplicate_prompt" in frame.get("qc_flags", []):
            errors.append(f"{frame.get('frame_id', '<unknown>')} still marked duplicate after rewrite")
    return errors, warnings


def validate_export_generator_queue(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    queue_path = file_must_exist(project["exports"].get("generator_queue_csv_path"), "exports.generator_queue_csv_path", errors)
    storyboard_path = file_must_exist(project["planning"].get("storyboard_frames_path"), "planning.storyboard_frames_path", errors)
    if not queue_path or not storyboard_path:
        return errors, warnings
    row_count = max(0, len(queue_path.read_text(encoding="utf-8").splitlines()) - 1)
    frame_count = len(load_json(storyboard_path).get("frames", []))
    if row_count != frame_count:
        errors.append("generator_queue row count does not match storyboard frame count")
    return errors, warnings


def validate_export_edit_timeline(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    timeline_path = file_must_exist(project["exports"].get("edit_timeline_csv_path"), "exports.edit_timeline_csv_path", errors)
    srt_path = file_must_exist(project["exports"].get("frame_timing_srt_path"), "exports.frame_timing_srt_path", errors)
    thumbs_path = file_must_exist(project["exports"].get("thumbnails_json_path"), "exports.thumbnails_json_path", errors)
    if not timeline_path or not srt_path or not thumbs_path:
        return errors, warnings
    if " --> " not in srt_path.read_text(encoding="utf-8"):
        errors.append("frame_timing.srt does not contain valid cue separators")
    candidates = load_json(thumbs_path).get("candidates", [])
    if not candidates:
        warnings.append("thumbnails.json contains no candidates")
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
    manifest_errors, manifest_warnings = validate_generation_manifest(manifest)
    errors.extend(manifest_errors)
    warnings.extend(manifest_warnings)
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
    edl_path = file_must_exist(project["render"].get("edit_decision_list_path"), "render.edit_decision_list_path", errors)
    if not ffconcat_path or not timeline_path or not edl_path:
        return errors, warnings
    timeline = load_json(timeline_path)
    edl_payload = load_json(edl_path)
    edl = edl_payload.get("edl", [])
    total_duration = sum(float(item.get("duration", 0) or 0) for item in timeline)
    audio_duration = float(project["inputs"].get("audio_duration_seconds") or 0)
    if audio_duration > 0 and abs(total_duration - audio_duration) > 0.2:
        errors.append(f"Timeline duration differs from audio by {abs(total_duration - audio_duration):.3f}s")
    if "ffconcat version 1.0" not in ffconcat_path.read_text(encoding="utf-8"):
        errors.append("ffconcat header is missing")
    previous_end = None
    for row in edl if isinstance(edl, list) else []:
        frame_id = row.get("frame_id", "<unknown>")
        if not str(row.get("beat_id", "")).strip():
            errors.append(f"{frame_id} missing beat_id in edit_decision_list")
        if not str(row.get("voice_text", "")).strip():
            errors.append(f"{frame_id} missing voice_text in edit_decision_list")
        if not str(row.get("visualized_claim", "")).strip():
            errors.append(f"{frame_id} missing visualized_claim in edit_decision_list")
        start = float(row.get("start", 0) or 0)
        end = float(row.get("end", 0) or 0)
        if end <= start:
            errors.append(f"{frame_id} has invalid EDL timing window")
        if previous_end is not None:
            if start > previous_end + 0.02:
                errors.append(f"{frame_id} introduces a timeline gap")
            if start < previous_end - 0.02:
                errors.append(f"{frame_id} overlaps previous EDL frame")
        previous_end = end
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
    "parse_srt": validate_parse_srt,
    "ingest_srt": validate_ingest_srt,
    "build_scene_map": validate_build_scene_map,
    "build_scenes": validate_build_scenes,
    "build_subscenes": validate_build_subscenes,
    "build_storyboard": validate_build_storyboard,
    "expand_storyboard": validate_expand_storyboard,
    "build_reference_prompt_pack": validate_build_reference_prompt_pack,
    "generate_reference_images": validate_generate_reference_images,
    "build_subject_registry": validate_build_subject_registry,
    "build_continuity_map": validate_build_continuity_map,
    "allocate_frames": validate_scene_plan,
    "build_narration_beats": validate_build_narration_beats,
    "author_narration_beats": validate_author_narration_beats,
    "build_visual_shot_plan": validate_build_visual_shot_plan,
    "build_frame_briefs": validate_build_frame_briefs,
    "attach_reference_assets": validate_attach_reference_assets,
    "entity_reference_lock": validate_entity_reference_lock,
    "scene_context_pack": validate_scene_context_pack,
    "directors_cut": validate_directors_cut,
    "write_prompts": validate_write_prompts,
    "generate_fastgen_prompt_drafts": validate_generate_fastgen_prompt_drafts,
    "generate_fastgen_prompts": validate_generate_fastgen_prompt_drafts,
    "generation_lock": validate_generation_lock,
    "qc": validate_qc,
    "quality_assurance": validate_quality_assurance,
    "rewrite_flagged": validate_rewrite_flagged,
    "export_montage_map": validate_export_montage_map,
    "export_generator_queue": validate_export_generator_queue,
    "export_edit_timeline": validate_export_edit_timeline,
    "export_generation_batches": validate_export_generation_batches,
    "report": validate_report,
    "motion_plan": validate_motion_plan,
    "final_review": validate_final_review,
    "images": validate_images,
    "image_qc": validate_image_qc,
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
