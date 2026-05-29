from __future__ import annotations


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

STAGE_TO_SECTION = {
    "transcription": "transcription",
    "cleanup_transcript_from_source": "transcript_cleanup",
    "ingest_srt": "planning",
    "build_scene_map": "planning",
    "expand_storyboard": "planning",
    "build_reference_prompt_pack": "planning",
    "generate_reference_images": "planning",
    "build_subject_registry": "planning",
    "build_continuity_map": "planning",
    "allocate_frames": "scene_plan",
    "build_narration_beats": "planning",
    "author_narration_beats": "planning",
    "build_visual_shot_plan": "prompts",
    "build_frame_briefs": "planning",
    "attach_reference_assets": "planning",
    "generate_fastgen_prompt_drafts": "prompts",
    "generation_lock": "prompts",
    "quality_assurance": "qc",
    "export_montage_map": "exports",
    "export_generation_batches": "prompts",
    "report": "qc",
    "motion_plan": "motion",
    "final_review": "qc",
    "publishing_package": "publishing",
    "generate_images": "images",
    "image_qc": "qc",
    "normalize_images": "images",
    "timeline": "render",
    "render": "render",
    "parse_srt": "planning",
    "build_scenes": "planning",
    "build_subscenes": "planning",
    "build_storyboard": "planning",
    "directors_cut": "prompts",
    "write_prompts": "prompts",
    "qc": "qc",
    "rewrite_flagged": "prompts",
    "export_generator_queue": "exports",
    "export_edit_timeline": "exports",
    "make_test_batch": "exports",
}


def normalize_stage_name(stage: str) -> str:
    return STAGE_ALIASES.get(stage, stage)


def stage_index(stage: str) -> int:
    return STAGE_SEQUENCE.index(normalize_stage_name(stage))


def stage_section_for_status(stage: str) -> str | None:
    return STAGE_TO_SECTION.get(normalize_stage_name(stage))
