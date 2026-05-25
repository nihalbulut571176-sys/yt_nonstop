import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGE_SEQUENCE = [
    "transcription",
    "cleanup_transcript_from_source",
    "scene_plan",
    "scene_qa",
    "narrative_enrichment",
    "style_bible",
    "visual_direction",
    "continuity_pass",
    "prompt_package",
    "scene_context_pack",
    "llm_prompt_drafts",
    "prompt_qa",
    "apply_llm_prompt_drafts",
    "motion_plan",
    "export_prompts",
    "final_review",
    "publishing_package",
    "generate_images",
    "normalize_images",
    "timeline",
    "render",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_project(project_json: Path) -> dict[str, Any]:
    project = load_json(project_json)
    project_root = Path(project.get("meta", {}).get("project_root", project_json.parent))

    def project_local_path(value: str | None, fallback: Path) -> str:
        if not value:
            return str(fallback)
        try:
            candidate = Path(value)
            candidate.relative_to(project_root)
            return str(candidate)
        except Exception:
            return str(fallback)

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
    prompts.setdefault("global_style_summary", None)
    prompts.setdefault("quality_mode", "standard")
    prompts.setdefault("visual_shot_plan_status", "pending")
    prompts.setdefault("authoring_model", "codex-gpt-5")

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

    project.setdefault("logs", {})
    logs = project["logs"]
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
    stage_to_section = {
        "transcription": "transcription",
        "cleanup_transcript_from_source": "transcript_cleanup",
        "scene_plan": "scene_plan",
        "scene_qa": "scene_plan",
        "narrative_enrichment": "scene_plan",
        "style_bible": "prompts",
        "visual_direction": "scene_plan",
        "continuity_pass": "prompts",
        "prompt_package": "prompts",
        "scene_context_pack": "prompts",
        "llm_prompt_drafts": "prompts",
        "prompt_qa": "prompts",
        "apply_llm_prompt_drafts": "prompts",
        "motion_plan": "motion",
        "final_review": "qc",
        "publishing_package": "publishing",
        "export_prompts": "prompts",
        "generate_images": "images",
        "normalize_images": "images",
        "timeline": "render",
        "render": "render",
    }
    section = stage_to_section.get(stage)
    if section:
        project[section]["status"] = status
    if current_stage:
        project["current_stage"] = current_stage


def stage_index(stage: str) -> int:
    return STAGE_SEQUENCE.index(stage)
