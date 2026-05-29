import json
from pathlib import Path
import re
from typing import Any

from yt_nonstop.pipeline.artifact_paths import (
    STAGE_ALIASES,
    STAGE_SEQUENCE,
    V2_STAGE_SEQUENCE,
    normalize_stage_name,
    stage_index,
    stage_section_for_status,
)
from yt_nonstop.utils.json_io import append_text, ensure_parent, iso_now, load_json, save_json


STAGE_SEQUENCE = [
    "transcription",
    "cleanup_transcript_from_source",
    "ingest_srt",
    "build_scene_map",
    "expand_storyboard",
    "build_continuity_map",
    "build_reference_prompt_pack",
    "generate_reference_images",
    "build_subject_registry",
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
    "publishing_package",
    "generate_images",
    "image_qc",
    "normalize_images",
    "timeline",
    "render",
]

V2_STAGE_SEQUENCE = [
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
]

STAGE_ALIASES = {
    "generate_fastgen_prompts": "generate_fastgen_prompt_drafts",
    "scene_context_pack": "generate_fastgen_prompt_drafts",
    "parse-srt": "parse_srt",
    "build-scenes": "build_scenes",
    "build-subscenes": "build_subscenes",
    "build-storyboard": "build_storyboard",
    "directors-cut": "directors_cut",
    "write-prompts": "write_prompts",
    "rewrite-flagged": "rewrite_flagged",
    "export-generator-queue": "export_generator_queue",
    "export-edit-timeline": "export_edit_timeline",
    "make-test-batch": "make_test_batch",
}


def normalize_path_text(value: str) -> str:
    return re.sub(r"/+", "/", str(value or "").strip().replace("\\", "/"))


def project_local_path(value: str | None, fallback: Path, project_root: Path) -> str:
    if not value:
        return str(fallback.resolve(strict=False))
    normalized_value = normalize_path_text(value)
    if not normalized_value:
        return str(fallback.resolve(strict=False))
    normalized_root = project_root.resolve(strict=False)
    normalized_root_text = normalize_path_text(normalized_root.as_posix()).lower()
    try:
        if re.match(r"^[A-Za-z]:/", normalized_value):
            if not normalized_root.drive:
                return str(fallback.resolve(strict=False))
            if not normalized_value.lower().startswith(normalized_root_text.rstrip("/") + "/") and normalized_value.lower() != normalized_root_text:
                return str(fallback.resolve(strict=False))
            candidate = Path(normalized_value)
        else:
            candidate = Path(normalized_value)
            if not candidate.is_absolute():
                candidate = normalized_root / candidate
        candidate = candidate.resolve(strict=False)
        candidate.relative_to(normalized_root)
        return str(candidate)
    except Exception:
        return str(fallback.resolve(strict=False))


def load_project(project_json: Path) -> dict[str, Any]:
    project = load_json(project_json)
    project_root = project_json.resolve().parent
    project.setdefault("meta", {})
    template_project_root = str(project["meta"].get("project_root") or "").strip()
    project["meta"]["project_root"] = str(project_root)

    def path_key(key: str) -> bool:
        return key.endswith(("_path", "_dir", "_root")) or key in {"audio_path"}

    def rebase_template_path(value: str) -> str:
        normalized_value = normalize_path_text(value)
        if not normalized_value:
            return normalized_value
        normalized_template_root = normalize_path_text(template_project_root)
        normalized_project_root = normalize_path_text(project_root.as_posix())
        lowered_value = normalized_value.lower()
        lowered_template_root = normalized_template_root.lower()
        if normalized_template_root and lowered_value == lowered_template_root:
            return normalized_project_root
        if normalized_template_root and lowered_value.startswith(lowered_template_root.rstrip("/") + "/"):
            suffix = normalized_value[len(normalized_template_root.rstrip("/")) :].lstrip("/")
            return str((project_root / Path(suffix)).resolve(strict=False))
        if re.match(r"^[A-Za-z]:/", normalized_value):
            return normalized_value
        candidate = Path(normalized_value)
        if candidate.is_absolute():
            return str(candidate.resolve(strict=False))
        return str((project_root / candidate).resolve(strict=False))

    def rebase_path_like_fields(payload: Any) -> Any:
        if isinstance(payload, dict):
            rewritten: dict[str, Any] = {}
            for key, value in payload.items():
                if isinstance(value, str) and path_key(key):
                    rewritten[key] = rebase_template_path(value)
                else:
                    rewritten[key] = rebase_path_like_fields(value)
            return rewritten
        if isinstance(payload, list):
            return [rebase_path_like_fields(item) for item in payload]
        return payload

    project = rebase_path_like_fields(project)

    def project_local_path(value: str | None, fallback: Path) -> str:
        return globals()["project_local_path"](value, fallback, project_root)

    project.setdefault("transcript_cleanup", {})
    cleanup = project["transcript_cleanup"]
    cleanup.setdefault("status", "pending")
    cleanup.setdefault("source_text_path", project.get("inputs", {}).get("raw_text_path"))
    cleanup.setdefault("used_source_path", None)
    cleanup["cleaned_srt_path"] = project_local_path(
        cleanup.get("cleaned_srt_path"),
        project_root / "transcript" / "cleaned.srt",
    )
    cleanup["cleaned_segments_json_path"] = project_local_path(
        cleanup.get("cleaned_segments_json_path"),
        project_root / "transcript" / "cleaned_segments.json",
    )
    cleanup["cleaned_timed_transcript_md_path"] = project_local_path(
        cleanup.get("cleaned_timed_transcript_md_path"),
        project_root / "transcript" / "cleaned_timed_transcript.md",
    )
    cleanup["cleanup_report_path"] = project_local_path(
        cleanup.get("cleanup_report_path"),
        project_root / "transcript" / "cleanup_report.json",
    )

    project.setdefault("prompts", {})
    prompts = project["prompts"]
    prompts["style_guide_path"] = project_local_path(
        prompts.get("style_guide_path"),
        project_root / "prompts" / "style_guide.json",
    )
    prompts["visual_bible_path"] = project_local_path(
        prompts.get("visual_bible_path"),
        project_root / "prompts" / "visual_bible.json",
    )
    prompts["visual_bible_review_path"] = project_local_path(
        prompts.get("visual_bible_review_path"),
        project_root / "prompts" / "visual_bible_review.md",
    )
    prompts["scene_context_pack_path"] = project_local_path(
        prompts.get("scene_context_pack_path"),
        project_root / "prompts" / "scene_context_pack.json",
    )
    prompts["visual_shot_plan_path"] = project_local_path(
        prompts.get("visual_shot_plan_path"),
        project_root / "prompts" / "visual_shot_plan.json",
    )
    prompts["shot_prompt_package_path"] = project_local_path(
        prompts.get("shot_prompt_package_path"),
        project_root / "prompts" / "shot_prompt_package.json",
    )
    prompts["shot_prompt_review_path"] = project_local_path(
        prompts.get("shot_prompt_review_path"),
        project_root / "prompts" / "shot_prompt_review.md",
    )
    prompts["llm_prompt_drafts_path"] = project_local_path(
        prompts.get("llm_prompt_drafts_path"),
        project_root / "prompts" / "llm_prompt_drafts.json",
    )
    prompts["prompt_package_path"] = project_local_path(
        prompts.get("prompt_package_path"),
        project_root / "prompts" / "prompt_package.json",
    )
    prompts["reference_mapping_path"] = project_local_path(
        prompts.get("reference_mapping_path"),
        project_root / "prompts" / "fastgen_ref_paths.json",
    )
    prompts["final_scene_plan_path"] = project_local_path(
        prompts.get("final_scene_plan_path"),
        project_root / "prompts" / "final_scene_plan.json",
    )
    prompts["fastgen_export_path"] = project_local_path(
        prompts.get("fastgen_export_path"),
        project_root / "exports" / "fastgen_prompts.md",
    )
    prompts["generator_ready_path"] = project_local_path(
        prompts.get("generator_ready_path"),
        project_root / "exports" / "fastgen_prompts.md",
    )
    prompts["prompt_review_path"] = project_local_path(
        prompts.get("prompt_review_path"),
        project_root / "prompts" / "prompt_review.md",
    )
    prompts["generation_locked_json_path"] = project_local_path(
        prompts.get("generation_locked_json_path"),
        project_root / "prompts" / "generation_locked_frames.json",
    )
    prompts["generation_locked_csv_path"] = project_local_path(
        prompts.get("generation_locked_csv_path"),
        project_root / "prompts" / "generation_locked_frames.csv",
    )
    prompts["directors_cut_review_path"] = project_local_path(
        prompts.get("directors_cut_review_path"),
        project_root / "prompts" / "directors_cut_review.json",
    )
    prompts["rewrite_queue_path"] = project_local_path(
        prompts.get("rewrite_queue_path"),
        project_root / "prompts" / "rewrite_queue.json",
    )
    prompts["subject_registry_path"] = project_local_path(
        prompts.get("subject_registry_path"),
        project_root / "prompts" / "subject_registry.json",
    )
    prompts["entity_registry_path"] = project_local_path(
        prompts.get("entity_registry_path"),
        project_root / "prompts" / "entity_registry.json",
    )
    prompts["reference_assets_manifest_path"] = project_local_path(
        prompts.get("reference_assets_manifest_path"),
        project_root / "prompts" / "reference_assets.json",
    )
    prompts["reference_prompt_pack_path"] = project_local_path(
        prompts.get("reference_prompt_pack_path"),
        project_root / "prompts" / "reference_prompt_pack.json",
    )
    prompts["reference_generation_manifest_path"] = project_local_path(
        prompts.get("reference_generation_manifest_path"),
        project_root / "prompts" / "reference_generation_manifest.json",
    )
    prompts.setdefault("global_style_summary", None)
    prompts.setdefault("quality_mode", "standard")
    prompts.setdefault("visual_shot_plan_status", "pending")
    prompts.setdefault("authoring_model", "codex-gpt-5")

    project.setdefault("workflow", {})
    workflow = project["workflow"]
    workflow.setdefault("task_type", "full_build")
    workflow.setdefault("is_sequence", True)
    workflow.setdefault("skip_storyboard_allowed", False)
    workflow.setdefault("requested_format", "json")
    workflow.setdefault("prompt_contract_version", "v1")
    workflow.setdefault("generation_lock_version", "lock-v1")
    workflow.setdefault("strict_generation_lock", False)

    project.setdefault("planning", {})
    planning = project["planning"]
    planning["scene_map_path"] = project_local_path(
        planning.get("scene_map_path"),
        project_root / "planning" / "scene_map.json",
    )
    planning["storyboard_path"] = project_local_path(
        planning.get("storyboard_path"),
        project_root / "planning" / "storyboard.json",
    )
    planning["frame_briefs_json_path"] = project_local_path(
        planning.get("frame_briefs_json_path"),
        project_root / "planning" / "frame_briefs.json",
    )
    planning["frame_briefs_csv_path"] = project_local_path(
        planning.get("frame_briefs_csv_path"),
        project_root / "planning" / "frame_briefs.csv",
    )
    planning["continuity_map_json_path"] = project_local_path(
        planning.get("continuity_map_json_path"),
        project_root / "config" / "continuity_entities.json",
    )
    planning["continuity_bible_md_path"] = project_local_path(
        planning.get("continuity_bible_md_path"),
        project_root / "config" / "continuity_bible.md",
    )
    planning["sentence_blocks_json_path"] = project_local_path(
        planning.get("sentence_blocks_json_path"),
        project_root / "planning" / "sentence_blocks.json",
    )
    planning["sentence_blocks_txt_path"] = project_local_path(
        planning.get("sentence_blocks_txt_path"),
        project_root / "planning" / "sentence_blocks.txt",
    )
    planning["global_scene_plan_path"] = project_local_path(
        planning.get("global_scene_plan_path"),
        project_root / "planning" / "global_scene_plan.json",
    )
    planning["subscene_plan_path"] = project_local_path(
        planning.get("subscene_plan_path"),
        project_root / "planning" / "subscene_plan.json",
    )
    planning["storyboard_frames_path"] = project_local_path(
        planning.get("storyboard_frames_path"),
        project_root / "planning" / "storyboard_frames.json",
    )
    planning["v2_project_skeleton_path"] = project_local_path(
        planning.get("v2_project_skeleton_path"),
        project_root / "planning" / "canonical_project.json",
    )
    planning["reference_binding_report_path"] = project_local_path(
        planning.get("reference_binding_report_path"),
        project_root / "planning" / "reference_binding_report.json",
    )
    planning["narration_beats_path"] = project_local_path(
        planning.get("narration_beats_path"),
        project_root / "planning" / "narration_beats.json",
    )
    planning["visual_allocation_plan_path"] = project_local_path(
        planning.get("visual_allocation_plan_path"),
        project_root / "planning" / "visual_allocation_plan.json",
    )
    planning.setdefault("narration_beats_status", "pending")
    planning.setdefault("v2_target_scene_count", 15)
    planning.setdefault("v2_chunk_size", 30)

    project.setdefault("assets", {})
    assets = project["assets"]
    assets["references_root"] = project_local_path(
        assets.get("references_root"),
        project_root / "assets" / "references",
    )
    assets["character_references_root"] = project_local_path(
        assets.get("character_references_root"),
        project_root / "assets" / "references" / "characters",
    )
    assets["reference_generation_run_root"] = project_local_path(
        assets.get("reference_generation_run_root"),
        project_root / "assets" / "references" / "fastgen_run",
    )

    project.setdefault("motion", {})
    motion = project["motion"]
    motion.setdefault("status", "pending")
    motion["motion_plan_json_path"] = project_local_path(
        motion.get("motion_plan_json_path"),
        project_root / "motion" / "motion_plan.json",
    )
    motion["motion_plan_csv_path"] = project_local_path(
        motion.get("motion_plan_csv_path"),
        project_root / "motion" / "motion_plan.csv",
    )

    project.setdefault("transcription", {})
    transcription = project["transcription"]
    transcription["srt_path"] = project_local_path(
        transcription.get("srt_path"),
        project_root / "transcript" / "raw_whisper.srt",
    )
    transcription["raw_srt_path"] = project_local_path(
        transcription.get("raw_srt_path"),
        project_root / "transcript" / "raw_whisper.srt",
    )

    project.setdefault("scene_plan", {})
    scene_plan = project["scene_plan"]
    scene_plan["source_srt_path"] = project_local_path(
        scene_plan.get("source_srt_path"),
        project_root / "transcript" / "cleaned.srt",
    )
    scene_plan["scene_plan_path"] = project_local_path(
        scene_plan.get("scene_plan_path"),
        project_root / "scene_plan" / "scene_plan.json",
    )
    scene_plan["long_segment_report_path"] = project_local_path(
        scene_plan.get("long_segment_report_path"),
        project_root / "scene_plan" / "long_segment_report.json",
    )

    project.setdefault("logs", {})
    logs = project["logs"]
    logs["pipeline_log_path"] = project_local_path(
        logs.get("pipeline_log_path"),
        project_root / "logs" / "pipeline.log",
    )
    logs["events_jsonl_path"] = project_local_path(
        logs.get("events_jsonl_path"),
        project_root / "logs" / "events.jsonl",
    )
    logs["input_validation_report_path"] = project_local_path(
        logs.get("input_validation_report_path"),
        project_root / "logs" / "input_validation_report.md",
    )
    logs["timing_cleanup_report_path"] = project_local_path(
        logs.get("timing_cleanup_report_path"),
        project_root / "logs" / "timing_cleanup_report.md",
    )
    logs["scene_qa_report_path"] = project_local_path(
        logs.get("scene_qa_report_path"),
        project_root / "logs" / "scene_qa_report.md",
    )
    logs["scene_qa_json_path"] = project_local_path(
        logs.get("scene_qa_json_path"),
        project_root / "logs" / "scene_qa.json",
    )
    logs["narrative_editor_report_path"] = project_local_path(
        logs.get("narrative_editor_report_path"),
        project_root / "logs" / "narrative_editor_report.md",
    )
    logs["visual_direction_report_path"] = project_local_path(
        logs.get("visual_direction_report_path"),
        project_root / "logs" / "visual_direction_report.md",
    )
    logs["brand_realism_report_path"] = project_local_path(
        logs.get("brand_realism_report_path"),
        project_root / "logs" / "brand_realism_report.md",
    )
    logs["prompt_qa_report_path"] = project_local_path(
        logs.get("prompt_qa_report_path"),
        project_root / "logs" / "prompt_qa_report.md",
    )
    logs["prompt_qa_json_path"] = project_local_path(
        logs.get("prompt_qa_json_path"),
        project_root / "logs" / "prompt_qa.json",
    )
    logs["export_report_path"] = project_local_path(
        logs.get("export_report_path"),
        project_root / "logs" / "export_report.md",
    )
    logs["generation_report_path"] = project_local_path(
        logs.get("generation_report_path"),
        project_root / "logs" / "generation_report.md",
    )
    logs["render_report_path"] = project_local_path(
        logs.get("render_report_path"),
        project_root / "logs" / "render_report.md",
    )
    logs["final_review_report_path"] = project_local_path(
        logs.get("final_review_report_path"),
        project_root / "logs" / "final_review_report.md",
    )
    logs["generation_lock_report_path"] = project_local_path(
        logs.get("generation_lock_report_path"),
        project_root / "logs" / "generation_lock_report.md",
    )
    logs["qa_report_json_path"] = project_local_path(
        logs.get("qa_report_json_path"),
        project_root / "logs" / "qa_report.json",
    )
    logs["workflow_report_path"] = project_local_path(
        logs.get("workflow_report_path"),
        project_root / "logs" / "workflow_report.md",
    )
    logs["workflow_report_json_path"] = project_local_path(
        logs.get("workflow_report_json_path"),
        project_root / "logs" / "workflow_report.json",
    )

    project.setdefault("exports", {})
    exports = project["exports"]
    exports["montage_timing_map_json_path"] = project_local_path(
        exports.get("montage_timing_map_json_path"),
        project_root / "exports" / "montage_timing_map.json",
    )
    exports["montage_timing_map_csv_path"] = project_local_path(
        exports.get("montage_timing_map_csv_path"),
        project_root / "exports" / "montage_timing_map.csv",
    )
    exports["montage_timing_map_xlsx_path"] = project_local_path(
        exports.get("montage_timing_map_xlsx_path"),
        project_root / "exports" / "montage_timing_map.xlsx",
    )

    exports["generator_queue_csv_path"] = project_local_path(
        exports.get("generator_queue_csv_path"),
        project_root / "exports" / "generator_queue.csv",
    )
    exports["edit_timeline_csv_path"] = project_local_path(
        exports.get("edit_timeline_csv_path"),
        project_root / "exports" / "edit_timeline.csv",
    )
    exports["frame_timing_srt_path"] = project_local_path(
        exports.get("frame_timing_srt_path"),
        project_root / "exports" / "frame_timing.srt",
    )
    exports["thumbnails_json_path"] = project_local_path(
        exports.get("thumbnails_json_path"),
        project_root / "exports" / "thumbnails.json",
    )

    project.setdefault("reports", {})
    reports = project["reports"]
    reports["qc_report_md_path"] = project_local_path(
        reports.get("qc_report_md_path"),
        project_root / "reports" / "qc_report.md",
    )
    reports["duplicate_report_csv_path"] = project_local_path(
        reports.get("duplicate_report_csv_path"),
        project_root / "reports" / "duplicate_report.csv",
    )
    reports["weak_frames_csv_path"] = project_local_path(
        reports.get("weak_frames_csv_path"),
        project_root / "reports" / "weak_frames.csv",
    )
    reports["production_report_json_path"] = project_local_path(
        reports.get("production_report_json_path"),
        project_root / "reports" / "production_report.json",
    )
    reports["production_report_md_path"] = project_local_path(
        reports.get("production_report_md_path"),
        project_root / "reports" / "production_report.md",
    )
    reports["generation_estimate_json_path"] = project_local_path(
        reports.get("generation_estimate_json_path"),
        project_root / "reports" / "generation_estimate.json",
    )
    reports["generation_estimate_md_path"] = project_local_path(
        reports.get("generation_estimate_md_path"),
        project_root / "reports" / "generation_estimate.md",
    )

    project.setdefault("qc", {})
    qc = project["qc"]
    qc["continuity_qc_report_path"] = project_local_path(
        qc.get("continuity_qc_report_path"),
        project_root / "qc" / "continuity_qc_report.json",
    )
    qc["review_applied_manifest_path"] = project_local_path(
        qc.get("review_applied_manifest_path"),
        project_root / "qc" / "review_applied_manifest.json",
    )
    qc["review_decisions_path"] = project_local_path(
        qc.get("review_decisions_path"),
        project_root / "qc" / "review_decisions.json",
    )
    qc["regeneration_plan_path"] = project_local_path(
        qc.get("regeneration_plan_path"),
        project_root / "qc" / "regeneration_plan.json",
    )
    qc["regeneration_execution_report_path"] = project_local_path(
        qc.get("regeneration_execution_report_path"),
        project_root / "qc" / "regeneration_execution_report.json",
    )
    qc["review_package_html_path"] = project_local_path(
        qc.get("review_package_html_path"),
        project_root / "qc" / "review_package.html",
    )

    project.setdefault("images", {})
    images = project["images"]
    images["run_manifest_path"] = project_local_path(
        images.get("run_manifest_path"),
        project_root / "images" / "run" / "run_manifest.json",
    )
    images["raw_images_dir"] = project_local_path(
        images.get("raw_images_dir"),
        project_root / "images" / "run",
    )
    images["normalized_images_dir"] = project_local_path(
        images.get("normalized_images_dir"),
        project_root / "images" / "normalized",
    )
    images["image_qc_report_path"] = project_local_path(
        images.get("image_qc_report_path"),
        project_root / "qc" / "image_qc_report.json",
    )
    images["selected_images_manifest_path"] = project_local_path(
        images.get("selected_images_manifest_path"),
        project_root / "qc" / "selected_images_manifest.json",
    )

    project.setdefault("render", {})
    render = project["render"]
    render["slideshow_timeline_path"] = project_local_path(
        render.get("slideshow_timeline_path"),
        project_root / "renders" / "slideshow_timeline.json",
    )
    render["render_report_json_path"] = project_local_path(
        render.get("render_report_json_path"),
        project_root / "logs" / "render_report.json",
    )
    render["ffconcat_path"] = project_local_path(
        render.get("ffconcat_path"),
        project_root / "renders" / "slideshow.ffconcat",
    )
    render["final_video_path"] = project_local_path(
        render.get("final_video_path"),
        project_root / "renders" / "final_video.mp4",
    )
    render["edit_decision_list_path"] = project_local_path(
        render.get("edit_decision_list_path"),
        project_root / "renders" / "edit_decision_list.json",
    )

    return project


def save_project(project_json: Path, project: dict[str, Any]) -> None:
    project["updated_at"] = iso_now()
    save_json(project_json, project)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_text(path: Path, text: str) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def append_event(project: dict[str, Any], event: dict[str, Any]) -> None:
    event_path = Path(project["logs"]["events_jsonl_path"])
    event["ts"] = iso_now()
    append_text(event_path, json.dumps(event, ensure_ascii=False) + "\n")


def append_log(project: dict[str, Any], message: str) -> None:
    log_path = Path(project["logs"]["pipeline_log_path"])
    append_text(log_path, f"[{iso_now()}] {message}\n")


def mark_stage(project: dict[str, Any], stage: str, status: str, current_stage: str | None = None) -> None:
    stage = normalize_stage_name(stage)
    section = stage_section_for_status(stage)
    if section:
        project[section]["status"] = status
    if current_stage:
        project["current_stage"] = current_stage


def normalize_stage_name(stage: str) -> str:
    return STAGE_ALIASES.get(stage, stage)


def stage_index(stage: str) -> int:
    return STAGE_SEQUENCE.index(normalize_stage_name(stage))
