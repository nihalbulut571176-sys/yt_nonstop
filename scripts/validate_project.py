import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project


STAGE_CHOICES = [
    "transcription",
    "transcript_quality",
    "scene_plan",
    "scene_qa",
    "prompt_package",
    "scene_context_pack",
    "llm_prompt_drafts",
    "prompt_qa",
    "motion_plan",
    "export_prompts",
    "final_review",
    "images",
    "normalized_images",
    "timeline",
    "render",
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


def validate_scene_qa(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    json_path = file_must_exist(project["logs"].get("scene_qa_json_path"), "logs.scene_qa_json_path", errors)
    if not json_path:
        return errors, warnings
    payload = load_json(json_path)
    errors.extend(payload.get("errors", []))
    warnings.extend(payload.get("warnings", []))
    return errors, warnings


def validate_prompt_package(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    package_path = file_must_exist(project["prompts"].get("prompt_package_path"), "prompts.prompt_package_path", errors)
    scene_plan_path = file_must_exist(project["scene_plan"].get("scene_plan_path"), "scene_plan.scene_plan_path", errors)
    if not package_path or not scene_plan_path:
        return errors, warnings
    package = load_json(package_path)
    items = package.get("items", [])
    scenes = load_json(scene_plan_path).get("scenes", [])
    scene_ids = {scene["scene_id"] for scene in scenes}
    if len(items) != len(scenes):
        errors.append(f"Prompt item count mismatch: {len(items)} items vs {len(scenes)} scenes")
    for item in items:
        if item.get("scene_id") not in scene_ids:
            errors.append(f"Prompt item references unknown scene_id: {item.get('scene_id')}")
        if not str(item.get("voice_text", "")).strip():
            warnings.append(f"{item.get('scene_id', '<unknown>')} has empty voice_text in prompt package")
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
    return errors, warnings


def validate_llm_prompt_drafts(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    drafts_path = file_must_exist(project["prompts"].get("llm_prompt_drafts_path"), "prompts.llm_prompt_drafts_path", errors)
    package_path = file_must_exist(project["prompts"].get("prompt_package_path"), "prompts.prompt_package_path", errors)
    if not drafts_path or not package_path:
        return errors, warnings
    drafts = load_json(drafts_path)
    package = load_json(package_path)
    package_scene_ids = {item["scene_id"] for item in package.get("items", [])}
    draft_scene_ids = set()
    required_fields = ["scene_id", "visual_goal", "final_prompt"]
    if not isinstance(drafts, list) or not drafts:
        errors.append("llm_prompt_drafts is empty or not a JSON array")
        return errors, warnings
    for record in drafts:
        scene_id = str(record.get("scene_id", "")).strip()
        if not scene_id:
            errors.append("llm_prompt_drafts record missing scene_id")
            continue
        draft_scene_ids.add(scene_id)
        for field in required_fields:
            if not str(record.get(field, "")).strip():
                errors.append(f"{scene_id} missing required field `{field}`")
    if draft_scene_ids != package_scene_ids:
        errors.append("llm_prompt_drafts scene coverage does not match prompt_package")
    return errors, warnings


def validate_prompt_qa(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    json_path = file_must_exist(project["logs"].get("prompt_qa_json_path"), "logs.prompt_qa_json_path", errors)
    if not json_path:
        return errors, warnings
    payload = load_json(json_path)
    errors.extend(payload.get("errors", []))
    warnings.extend(payload.get("warnings", []))
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


def validate_export_prompts(project: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    export_path = file_must_exist(project["prompts"].get("fastgen_export_path"), "prompts.fastgen_export_path", errors)
    final_scene_plan_path = Path(project["prompts"].get("final_scene_plan_path") or "")
    source_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    if not export_path or not source_path.exists():
        if not source_path.exists():
            errors.append(f"Missing source scene plan for export validation: {source_path}")
        return errors, warnings
    scene_count = len(load_json(source_path).get("scenes", []))
    blocks = [block.strip() for block in export_path.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    if len(blocks) != scene_count:
        errors.append(f"Generator-ready block count mismatch: {len(blocks)} blocks vs {scene_count} scenes")
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
    "scene_plan": validate_scene_plan,
    "scene_qa": validate_scene_qa,
    "prompt_package": validate_prompt_package,
    "scene_context_pack": validate_scene_context_pack,
    "llm_prompt_drafts": validate_llm_prompt_drafts,
    "prompt_qa": validate_prompt_qa,
    "motion_plan": validate_motion_plan,
    "export_prompts": validate_export_prompts,
    "final_review": validate_final_review,
    "images": validate_images,
    "normalized_images": validate_normalized_images,
    "timeline": validate_timeline,
    "render": validate_render,
}


def write_report(project_json: Path, project: dict[str, Any], payload: dict[str, Any]) -> None:
    report_path = Path(project["qc"]["qc_report_path"])
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
    stages = list(VALIDATORS.keys()) if args.stage == "all" else [args.stage]
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
