import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from llm_pipeline_contracts import build_generation_job_id, classify_generation_error, compute_prompt_hash, inspect_image_file, iso_now
from pipeline_contracts import stable_hash
from project_pipeline_utils import append_event, append_log, load_json, load_project, mark_stage, save_json, save_project
from fastgen_openai_v4_generate import parse_prompt_blocks
from yt_nonstop.pipeline.pilot_profiles import active_profile_name, effective_limit_frames, resolve_runtime_profile
from yt_nonstop.pipeline.real_generation_preflight import run_real_generation_preflight
from pipeline_state import (
    DEFAULT_STAGE,
    connect as connect_state_db,
    get_frame_state,
    resolve_state_db_path,
    summarize_states,
    upsert_frame_state,
)


ROOT = Path(__file__).resolve().parents[1]


def load_failed_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def build_failed_lookup(records: list[dict]) -> dict[int, dict]:
    return {
        int(record["index"]): {
            "error_message": str(record.get("error", "")),
            "error_type": str(record.get("error_type") or classify_generation_error(str(record.get("error", "")))),
        }
        for record in records
        if "index" in record
    }


def extract_policy_failed_indices(records: list[dict]) -> list[int]:
    policy_markers = [
        "content polic",
        "guardrails around violence",
        "policy",
        "violence",
    ]
    indices: list[int] = []
    for record in records:
        message = str(record.get("error", "")).lower()
        if any(marker in message for marker in policy_markers):
            indices.append(int(record["index"]))
    return sorted(set(indices))


def build_scene_lookup(prompt_file: Path, scene_plan: dict, package: dict) -> tuple[dict[int, str], dict[str, dict]]:
    scene_by_prompt_index: dict[int, str] = {}
    meta_path = prompt_file.with_suffix(prompt_file.suffix + ".meta.json")
    meta_items = []
    if meta_path.exists():
        meta_items = load_json(meta_path).get("package_items", [])
    source_items = meta_items or package.get("items", [])
    for prompt_index, item in enumerate(source_items, start=1):
        scene_by_prompt_index[prompt_index] = item["scene_id"]

    scene_map = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", [])}
    return scene_by_prompt_index, scene_map


def load_prompt_meta(prompt_file: Path) -> list[dict[str, Any]]:
    meta_path = prompt_file.with_suffix(prompt_file.suffix + ".meta.json")
    if not meta_path.exists():
        return []
    return load_json(meta_path).get("package_items", [])


def prompt_block_text(item: dict[str, Any]) -> str:
    refs = list(item.get("refs", []))
    prompt = str(item.get("prompt", "")).strip()
    if not refs:
        return f"No character reference. {prompt}"
    if len(refs) == 1:
        return f"Use reference image: {refs[0]}. {prompt}"
    return f"Use reference images: {', '.join(refs)}. {prompt}"


def build_subset_prompt_export(
    *,
    prompt_file: Path,
    selected_source_indices: list[int],
) -> Path:
    parsed = parse_prompt_blocks(prompt_file)
    meta = load_prompt_meta(prompt_file)
    selected = [
        {
            "parsed": parsed[index - 1],
            "meta": meta[index - 1] if index - 1 < len(meta) else {},
        }
        for index in selected_source_indices
        if 1 <= index <= len(parsed)
    ]
    if not selected:
        raise RuntimeError("No prompt blocks selected for limited pilot generation")

    subset_path = prompt_file.parent / "fastgen_prompts.pilot_subset.md"
    subset_blocks = [prompt_block_text(item["parsed"]) for item in selected]
    subset_text = "\n\n".join(subset_blocks).strip() + "\n"
    package_items = []
    for local_index, item in enumerate(selected, start=1):
        package_row = dict(item["meta"])
        package_row.setdefault("scene_id", f"scene_{local_index:04d}")
        package_row["source_prompt_index"] = int(item["parsed"]["index"])
        package_items.append(package_row)
    package_signature = stable_hash(
        {
            "eligible_frames": [row.get("frame_id") for row in package_items],
            "items": package_items,
        }
    )
    meta_payload = {
        "package_path": str(subset_path.with_suffix(".json")),
        "package_signature": package_signature,
        "prompt_count": len(package_items),
        "non_generative_frame_count": 0,
        "package_items": package_items,
    }
    meta_payload["export_signature"] = stable_hash(
        {
            "package_path": meta_payload["package_path"],
            "package_signature": meta_payload["package_signature"],
            "prompt_count": meta_payload["prompt_count"],
            "content": subset_text,
        }
    )
    subset_path.write_text(subset_text, encoding="utf-8")
    subset_path.with_suffix(subset_path.suffix + ".meta.json").write_text(
        json.dumps(meta_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return subset_path


def load_existing_manifest_source_indices(run_manifest_path: Path) -> list[int]:
    if not run_manifest_path.exists():
        return []
    payload = load_json(run_manifest_path)
    indices = []
    if isinstance(payload, dict):
        rows = payload.get("generated_images", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    for item in rows:
        value = int(item.get("source_prompt_index", 0) or 0)
        if value > 0:
            indices.append(value)
    return sorted(set(indices))


def load_touched_state_source_indices(
    *,
    state_db_path: Path,
    project_id: str,
    prompt_file: Path,
    stage: str = DEFAULT_STAGE,
) -> list[int]:
    meta = load_prompt_meta(prompt_file)
    touched: list[int] = []
    conn = connect_state_db(state_db_path)
    try:
        for source_index, meta_row in enumerate(meta, start=1):
            frame_id = str(meta_row.get("frame_id") or "")
            if not frame_id:
                continue
            state = get_frame_state(
                conn,
                project_id=project_id,
                frame_id=frame_id,
                visual_slot_id=str(meta_row.get("visual_slot_id") or ""),
                stage=stage,
            )
            if state and state.status != "pending":
                touched.append(source_index)
    finally:
        conn.close()
    return sorted(set(touched))


def existing_image_path(workdir: Path, scene_id: str, variant_count: int) -> Path | None:
    for variant_index in range(1, max(1, variant_count) + 1):
        candidate = workdir / "images" / f"{scene_id}_V{variant_index:02d}.png"
        if candidate.exists():
            return candidate
    return None


def select_generation_items(
    *,
    state_db_path: Path,
    project_id: str,
    prompt_file: Path,
    workdir: Path,
    limit_frames: int | None,
    retry_failed_only: bool,
    requested_frame_ids: list[str],
) -> dict[str, Any]:
    parsed = parse_prompt_blocks(prompt_file)
    meta = load_prompt_meta(prompt_file)
    requested_ids = {item.strip() for item in requested_frame_ids if str(item).strip()}
    selected_source_indices: list[int] = []
    selected_frame_ids: list[str] = []
    skipped_existing_success_count = 0
    skipped_due_to_limit_count = 0
    pending_candidates: list[dict[str, Any]] = []
    total_generative_frames = len(meta) if meta else len(parsed)
    non_generative_slots_count = int(load_json(prompt_file.with_suffix(prompt_file.suffix + ".meta.json")).get("non_generative_frame_count", 0) or 0) if prompt_file.with_suffix(prompt_file.suffix + ".meta.json").exists() else 0
    conn = connect_state_db(state_db_path)
    try:
        for source_index, parsed_row in enumerate(parsed, start=1):
            meta_row = meta[source_index - 1] if source_index - 1 < len(meta) else {}
            frame_id = str(meta_row.get("frame_id") or "")
            visual_slot_id = str(meta_row.get("visual_slot_id") or "")
            scene_id = str(meta_row.get("scene_id") or f"scene_{source_index:04d}")
            variant_count = max(1, int(meta_row.get("variant_count", 1) or 1))
            state = get_frame_state(
                conn,
                project_id=project_id,
                frame_id=frame_id,
                visual_slot_id=visual_slot_id,
                stage=DEFAULT_STAGE,
            ) if frame_id else None
            existing_image = existing_image_path(workdir, scene_id, variant_count)
            is_success = bool(state and state.status == "success" and state.image_path and Path(state.image_path).exists()) or existing_image is not None
            if requested_ids and frame_id not in requested_ids:
                continue
            if is_success:
                skipped_existing_success_count += 1
                continue
            if retry_failed_only:
                if not state or state.status not in {"failed", "missing"}:
                    continue
            pending_candidates.append(
                {
                    "source_index": source_index,
                    "frame_id": frame_id,
                    "scene_id": scene_id,
                }
            )
        allowed = int(limit_frames or 0)
        for candidate in pending_candidates:
            if allowed > 0 and len(selected_source_indices) >= allowed:
                skipped_due_to_limit_count += 1
                continue
            selected_source_indices.append(candidate["source_index"])
            if candidate["frame_id"]:
                selected_frame_ids.append(candidate["frame_id"])
    finally:
        conn.close()

    return {
        "selected_source_indices": selected_source_indices,
        "selected_frame_ids": selected_frame_ids,
        "skipped_existing_success_count": skipped_existing_success_count,
        "skipped_due_to_limit_count": skipped_due_to_limit_count,
        "non_generative_slots_count": non_generative_slots_count,
        "planned_generative_frames_count": total_generative_frames,
        "pending_candidates_count": len(pending_candidates),
    }


def sync_generation_state(
    *,
    state_db_path: Path,
    project_id: str,
    prompt_file: Path,
    prompt_profile: dict[str, Any],
    stage: str = DEFAULT_STAGE,
) -> dict[str, Any]:
    prompt_items = parse_prompt_blocks(prompt_file)
    prompt_meta = load_prompt_meta(prompt_file)
    conn = connect_state_db(state_db_path)
    try:
        for item in prompt_items:
            meta = prompt_meta[item["index"] - 1] if item["index"] - 1 < len(prompt_meta) else {}
            frame_id = str(meta.get("frame_id") or "")
            if not frame_id:
                continue
            prompt_hash = compute_prompt_hash(prompt=item["prompt"], refs=item.get("refs", []), settings=prompt_profile)
            upsert_frame_state(
                conn,
                project_id=project_id,
                frame_id=frame_id,
                visual_slot_id=str(meta.get("visual_slot_id") or ""),
                stage=stage,
                status="pending",
                prompt_hash=prompt_hash,
            )
        return summarize_states(conn.execute("SELECT * FROM frame_state WHERE project_id = ? AND stage = ?", (project_id, stage)).fetchall())
    finally:
        conn.close()


def build_enriched_manifest_from_state(
    *,
    state_db_path: Path,
    project: dict,
    project_id: str,
    job_id: str,
    created_at: str,
    prompt_file: Path,
    workdir: Path,
    prompt_profile: dict[str, Any],
    scene_plan: dict,
    scene_map: dict[str, dict],
    failed_lookup: dict[int, dict],
    stage: str = DEFAULT_STAGE,
) -> dict[str, Any]:
    prompt_items = parse_prompt_blocks(prompt_file)
    prompt_meta = load_prompt_meta(prompt_file)
    generated_images = []
    conn = connect_state_db(state_db_path)
    try:
        for item in prompt_items:
            meta = prompt_meta[item["index"] - 1] if item["index"] - 1 < len(prompt_meta) else {}
            scene_id = str(meta.get("scene_id") or f"scene_{item['index']:04d}")
            frame_id = str(meta.get("frame_id") or "")
            visual_slot_id = str(meta.get("visual_slot_id") or "")
            variant_count = max(1, int(meta.get("variant_count", 1) or 1))
            prompt_hash = compute_prompt_hash(prompt=item["prompt"], refs=item.get("refs", []), settings=prompt_profile)
            state = get_frame_state(conn, project_id=project_id, frame_id=frame_id, visual_slot_id=visual_slot_id, stage=stage) if frame_id else None
            for variant_index in range(1, variant_count + 1):
                output_file = f"{scene_id}_V{variant_index:02d}.png"
                default_image_path = workdir / "images" / output_file
                image_path = Path(state.image_path) if state and state.image_path else default_image_path
                failed_meta = failed_lookup.get(item["index"], {})
                if state and state.status == "success" and image_path.exists():
                    status = "success"
                    error_type = ""
                    error_message = ""
                elif default_image_path.exists():
                    status = "success"
                    image_path = default_image_path
                    error_type = ""
                    error_message = ""
                elif state and state.status == "failed":
                    status = "failed"
                    error_type = failed_meta.get("error_type") or classify_generation_error(state.error_message)
                    error_message = state.error_message or failed_meta.get("error_message", "")
                else:
                    status = "missing"
                    error_type = "filesystem_error"
                    error_message = "Image file missing after generation run or interrupted generation"
                image_info = inspect_image_file(image_path) if status == "success" else {}
                generated_images.append(
                    {
                        "job_id": job_id,
                        "created_at": created_at,
                        "scene_id": scene_id,
                        "frame_id": frame_id,
                        "visual_slot_id": visual_slot_id,
                        "source_prompt_index": item["index"],
                        "variant_index": variant_index,
                        "variant_label": f"V{variant_index:02d}",
                        "prompt_hash": prompt_hash,
                        "generator_profile": stable_hash(prompt_profile),
                        "generator_settings": prompt_profile,
                        "refs": item.get("refs", []),
                        "prompt": item.get("prompt", ""),
                        "output_file": output_file,
                        "image_path": str(image_path),
                        "beat_priority": meta.get("beat_priority", "standard"),
                        "key_beat": bool(meta.get("key_beat")),
                        "variant_count": variant_count,
                        "selection_required": bool(meta.get("key_beat")) or variant_count > 1,
                        "status": status,
                        "error_type": error_type,
                        "error_message": error_message,
                        "image_format": image_info.get("format"),
                        "image_width": image_info.get("width"),
                        "image_height": image_info.get("height"),
                    }
                )

                scene = scene_map.get(scene_id)
                if scene and status == "success":
                    scene["generated_index"] = item["index"]
                    scene["still_image_path"] = str(image_path)
                    scene["render_source"] = "still"
                    scene["render_asset_path"] = str(image_path)
                    notes = [note for note in scene.get("notes", []) if note != "Still image pending"]
                    if "Generated image ready" not in notes:
                        notes.append("Generated image ready")
                    scene["notes"] = notes

    finally:
        conn.close()

    return {
        "project_id": project_id,
        "job_id": job_id,
        "created_at": created_at,
        "profile_id": project["profile_id"],
        "prompt_file": str(prompt_file),
        "workdir": str(workdir),
        "state_db_path": str(state_db_path),
        "generator_profile": prompt_profile,
        "generated_images": generated_images,
        "failed_count": sum(1 for item in generated_images if item["status"] == "failed"),
        "completed_count": sum(1 for item in generated_images if item["status"] == "success"),
        "missing_count": sum(1 for item in generated_images if item["status"] == "missing"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--retry-rounds", type=int, default=3)
    parser.add_argument("--soften-policy-prompts", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Use pipeline_state.sqlite to skip successful frames and continue interrupted runs.")
    parser.add_argument("--retry-failed-only", action="store_true", help="Regenerate only frames currently marked failed in pipeline_state.sqlite.")
    parser.add_argument("--frame-id", action="append", default=[], help="Regenerate a specific frame_id; can be repeated.")
    parser.add_argument("--state-db", default="", help="Override pipeline_state.sqlite path.")
    parser.add_argument("--profile", default="")
    parser.add_argument("--real-generation", action="store_true")
    parser.add_argument("--limit-frames", type=int, default=0)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    prompt_file = Path(project["prompts"]["fastgen_export_path"])
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    scene_plan_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    workdir = Path(project["images"]["run_manifest_path"]).parent
    workdir.mkdir(parents=True, exist_ok=True)

    if not prompt_file.exists():
        raise FileNotFoundError(f"Generator-ready prompt file not found: {prompt_file}")
    if not prompt_package_path.exists():
        raise FileNotFoundError(f"Prompt package not found: {prompt_package_path}")
    if not scene_plan_path.exists():
        raise FileNotFoundError(f"Scene plan not found: {scene_plan_path}")

    state_db_path = resolve_state_db_path(project_json, project, args.state_db or None)
    project.setdefault("state", {})["pipeline_state_path"] = str(state_db_path)
    runtime_profile = resolve_runtime_profile(active_profile_name(project, args.profile))
    effective_limit = effective_limit_frames(project, args.limit_frames, runtime_profile)
    project.setdefault("runtime", {})["active_profile"] = runtime_profile.name if runtime_profile else active_profile_name(project, args.profile)
    project["runtime"]["limit_frames"] = int(effective_limit or 0)
    project["runtime"]["real_generation"] = bool(args.real_generation)
    prompt_profile = {
        "provider": "fastgen_openai_v4",
        "size": args.size,
        "aspect_ratio": args.aspect_ratio,
    }
    sync_summary = sync_generation_state(
        state_db_path=state_db_path,
        project_id=project["project_id"],
        prompt_file=prompt_file,
        prompt_profile=prompt_profile,
    )
    selection = select_generation_items(
        state_db_path=state_db_path,
        project_id=project["project_id"],
        prompt_file=prompt_file,
        workdir=workdir,
        limit_frames=effective_limit,
        retry_failed_only=args.retry_failed_only,
        requested_frame_ids=args.frame_id,
    )
    selected_source_indices = selection["selected_source_indices"]
    limited_pilot = bool(args.real_generation and effective_limit and effective_limit > 0)
    started_at = iso_now()

    if (args.resume or args.retry_failed_only or args.frame_id or effective_limit) and int(sync_summary.get("total", 0) or 0) > 0 and not selected_source_indices:
        by_status = sync_summary.get("by_status", {}) or {}
        pending_like = sum(int(by_status.get(key, 0) or 0) for key in ("pending", "running", "failed", "missing"))
        if pending_like == 0 or selection["pending_candidates_count"] == 0:
            prompt_package = load_json(prompt_package_path)
            scene_plan = load_json(scene_plan_path)
            job_id = build_generation_job_id(project["project_id"])
            created_at = iso_now()
            run_manifest_path = Path(project["images"]["run_manifest_path"])
            manifest_source_indices = sorted(
                set(
                    load_existing_manifest_source_indices(run_manifest_path)
                    + load_touched_state_source_indices(
                        state_db_path=state_db_path,
                        project_id=project["project_id"],
                        prompt_file=prompt_file,
                    )
                    + selected_source_indices
                )
            )
            manifest_prompt_file = build_subset_prompt_export(
                prompt_file=prompt_file,
                selected_source_indices=manifest_source_indices,
            ) if manifest_source_indices else prompt_file
            _, scene_map = build_scene_lookup(manifest_prompt_file, scene_plan, prompt_package)
            enriched_manifest = build_enriched_manifest_from_state(
                state_db_path=state_db_path,
                project=project,
                project_id=project["project_id"],
                job_id=job_id,
                created_at=created_at,
                prompt_file=manifest_prompt_file,
                workdir=workdir,
                prompt_profile=prompt_profile,
                scene_plan=scene_plan,
                scene_map=scene_map,
                failed_lookup={},
            )
            manifest_touched_count = len(manifest_source_indices)
            deferred_due_limit_count = int(selection["skipped_due_to_limit_count"] or 0)
            if limited_pilot and deferred_due_limit_count == 0:
                deferred_due_limit_count = max(0, int(selection["planned_generative_frames_count"] or 0) - manifest_touched_count)
            effective_manifest_limit = int(effective_limit or 0)
            if args.retry_failed_only and not args.limit_frames and manifest_touched_count > 0:
                effective_manifest_limit = manifest_touched_count
            enriched_manifest["limited_pilot"] = limited_pilot
            enriched_manifest["partial_pilot"] = bool(limited_pilot and selection["planned_generative_frames_count"] > enriched_manifest["completed_count"])
            enriched_manifest["real_generation"] = bool(args.real_generation)
            enriched_manifest["profile"] = runtime_profile.name if runtime_profile else active_profile_name(project, args.profile)
            enriched_manifest["limit_frames"] = effective_manifest_limit
            enriched_manifest["generated_count"] = int(enriched_manifest["completed_count"])
            enriched_manifest["skipped_existing_success_count"] = int(selection["skipped_existing_success_count"])
            enriched_manifest["skipped_due_to_limit_count"] = deferred_due_limit_count
            enriched_manifest["non_generative_slots_count"] = int(selection["non_generative_slots_count"])
            enriched_manifest["provider"] = "fastgen_openai_v4"
            enriched_manifest["started_at"] = started_at
            enriched_manifest["finished_at"] = iso_now()
            enriched_manifest["planned_generative_frames_count"] = int(selection["planned_generative_frames_count"])
            save_json(run_manifest_path, enriched_manifest)
            save_json(scene_plan_path, scene_plan)
            if enriched_manifest.get("partial_pilot"):
                project["images"]["status"] = "pilot_partial"
            else:
                project["images"]["status"] = "generated"
            project["images"]["job_id"] = job_id
            project["images"]["generated_count"] = enriched_manifest["completed_count"]
            project["images"]["failed_count"] = enriched_manifest["failed_count"]
            project["images"]["missing_count"] = enriched_manifest.get("missing_count", 0)
            project["images"]["state_db_path"] = str(state_db_path)
            project["images"]["limited_pilot"] = bool(enriched_manifest.get("limited_pilot"))
            project["images"]["partial_pilot"] = bool(enriched_manifest.get("partial_pilot"))
            project["images"]["limit_frames"] = int(enriched_manifest.get("limit_frames", 0) or 0)
            project["current_stage"] = "image_qc"
            save_project(project_json, project)
            print(run_manifest_path)
            return

    if selected_source_indices:
        run_real_generation_preflight(
            project_json=project_json,
            project=project,
            profile=runtime_profile,
            real_generation=args.real_generation,
            limit_frames=effective_limit,
        )
    else:
        if not args.real_generation and int(selection["planned_generative_frames_count"] or 0) > int(selection["skipped_existing_success_count"] or 0):
            raise RuntimeError("Real FastGen pilot requires --real-generation before any external image API call")

    append_log(project, f"Starting FastGen generation in {workdir}; state={state_db_path}; state_summary={sync_summary}")
    append_event(project, {"kind": "stage_start", "stage": "generate_images", "state_db_path": str(state_db_path), "state_summary": sync_summary})
    mark_stage(project, "generate_images", "running", current_stage="generate_images")
    save_project(project_json, project)

    execution_prompt_file = build_subset_prompt_export(
        prompt_file=prompt_file,
        selected_source_indices=selected_source_indices,
    ) if selected_source_indices else prompt_file

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "fastgen_openai_v4_generate.py"),
        "--prompts",
        str(execution_prompt_file),
        "--refs",
        project["prompts"]["reference_mapping_path"],
        "--workdir",
        str(workdir),
        "--size",
        args.size,
        "--aspect-ratio",
        args.aspect_ratio,
        "--state-db",
        str(state_db_path),
        "--project-id",
        project["project_id"],
        "--state-stage",
        DEFAULT_STAGE,
        "--start",
        str(args.start),
        "--poll-seconds",
        str(args.poll_seconds),
        "--max-polls",
        str(args.max_polls),
        "--concurrency",
        str(args.concurrency),
    ]
    if args.end > 0:
        cmd.extend(["--end", str(args.end)])
    if args.stop_on_error:
        cmd.append("--stop-on-error")
    if args.resume:
        cmd.append("--resume")
    if args.retry_failed_only:
        cmd.append("--retry-failed-only")
    for frame_id in args.frame_id:
        cmd.extend(["--frame-id", frame_id])

    retry_rounds = max(1, args.retry_rounds)
    failed_path = workdir / "failed.jsonl"
    last_failed_records: list[dict] = []
    job_id = build_generation_job_id(project["project_id"])
    created_at = iso_now()

    for round_index in range(1, retry_rounds + 1):
        append_log(project, f"FastGen attempt {round_index}/{retry_rounds}")
        if failed_path.exists():
            failed_path.unlink()
        subprocess.run(cmd, check=True)
        last_failed_records = load_failed_records(failed_path)
        if not last_failed_records:
            break
        if round_index >= retry_rounds:
            break

        policy_failed_indices = extract_policy_failed_indices(last_failed_records)
        if policy_failed_indices and args.soften_policy_prompts:
            indices_path = workdir / "policy_failed_indices.json"
            indices_path.write_text(json.dumps(policy_failed_indices, ensure_ascii=False, indent=2), encoding="utf-8")
            soften_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "soften_failed_image_prompts.py"),
                "--project-json",
                str(project_json),
                "--indices-json",
                str(indices_path),
            ]
            subprocess.run(soften_cmd, check=True)
            export_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "export_project_fastgen_prompts.py"),
                "--project-json",
                str(project_json),
            ]
            subprocess.run(export_cmd, check=True)

    project = load_project(project_json)
    run_manifest_path = Path(project["images"]["run_manifest_path"])
    run_summary_path = workdir / "run_summary.json"
    run_summary = load_json(run_summary_path) if run_summary_path.exists() else {"done": 0, "skipped": 0, "failed": 0, "filtered": 0}
    prompt_package = load_json(prompt_package_path)
    scene_plan = load_json(scene_plan_path)
    manifest_source_indices = sorted(
        set(
            load_existing_manifest_source_indices(run_manifest_path)
            + load_touched_state_source_indices(
                state_db_path=state_db_path,
                project_id=project["project_id"],
                prompt_file=prompt_file,
            )
            + selected_source_indices
        )
    )
    manifest_prompt_file = build_subset_prompt_export(
        prompt_file=prompt_file,
        selected_source_indices=manifest_source_indices,
    ) if manifest_source_indices else execution_prompt_file
    _, scene_map = build_scene_lookup(manifest_prompt_file, scene_plan, prompt_package)
    failed_lookup = build_failed_lookup(last_failed_records)

    enriched_manifest = build_enriched_manifest_from_state(
        state_db_path=state_db_path,
        project=project,
        project_id=project["project_id"],
        job_id=job_id,
        created_at=created_at,
        prompt_file=manifest_prompt_file,
        workdir=workdir,
        prompt_profile=prompt_profile,
        scene_plan=scene_plan,
        scene_map=scene_map,
        failed_lookup=failed_lookup,
    )
    manifest_touched_count = len(manifest_source_indices)
    deferred_due_limit_count = int(selection["skipped_due_to_limit_count"] or 0)
    if limited_pilot and deferred_due_limit_count == 0:
        deferred_due_limit_count = max(0, int(selection["planned_generative_frames_count"] or 0) - manifest_touched_count)
    effective_manifest_limit = int(effective_limit or 0)
    if args.retry_failed_only and not args.limit_frames and manifest_touched_count > 0:
        effective_manifest_limit = manifest_touched_count
    enriched_manifest["skipped_count"] = int(run_summary.get("skipped", 0) or 0)
    enriched_manifest["filtered_count"] = int(run_summary.get("filtered", 0) or 0)
    enriched_manifest["retry_rounds_used"] = retry_rounds
    enriched_manifest["limited_pilot"] = limited_pilot
    enriched_manifest["real_generation"] = bool(args.real_generation)
    enriched_manifest["profile"] = runtime_profile.name if runtime_profile else active_profile_name(project, args.profile)
    enriched_manifest["limit_frames"] = effective_manifest_limit
    enriched_manifest["generated_count"] = int(enriched_manifest["completed_count"])
    enriched_manifest["skipped_existing_success_count"] = int(selection["skipped_existing_success_count"])
    enriched_manifest["skipped_due_to_limit_count"] = deferred_due_limit_count
    enriched_manifest["non_generative_slots_count"] = int(selection["non_generative_slots_count"])
    enriched_manifest["provider"] = "fastgen_openai_v4"
    enriched_manifest["started_at"] = started_at
    enriched_manifest["finished_at"] = iso_now()
    enriched_manifest["planned_generative_frames_count"] = int(selection["planned_generative_frames_count"])
    enriched_manifest["partial_pilot"] = bool(
        limited_pilot
        and (
            int(selection["skipped_due_to_limit_count"] or 0) > 0
            or (int(enriched_manifest["completed_count"]) + int(selection["skipped_existing_success_count"])) < int(selection["planned_generative_frames_count"])
        )
    )
    save_json(run_manifest_path, enriched_manifest)
    save_json(scene_plan_path, scene_plan)

    incomplete_count = int(enriched_manifest.get("failed_count", 0) or 0) + int(enriched_manifest.get("missing_count", 0) or 0)
    if enriched_manifest.get("partial_pilot"):
        project["images"]["status"] = "pilot_partial"
    else:
        project["images"]["status"] = "generated" if incomplete_count == 0 else "partial"
    project["images"]["job_id"] = job_id
    project["images"]["generated_count"] = enriched_manifest["completed_count"]
    project["images"]["failed_count"] = enriched_manifest["failed_count"]
    project["images"]["missing_count"] = enriched_manifest.get("missing_count", 0)
    project["images"]["state_db_path"] = str(state_db_path)
    project["images"]["limited_pilot"] = bool(enriched_manifest.get("limited_pilot"))
    project["images"]["partial_pilot"] = bool(enriched_manifest.get("partial_pilot"))
    project["images"]["limit_frames"] = int(enriched_manifest.get("limit_frames", 0) or 0)
    project["current_stage"] = "image_qc" if incomplete_count == 0 else "generate_images"
    save_project(project_json, project)
    append_event(project, {"kind": "stage_end", "stage": "generate_images", "status": project["images"]["status"], "incomplete_count": incomplete_count})
    append_log(project, f"FastGen generation completed: {enriched_manifest['completed_count']} images ready; incomplete={incomplete_count}")

    print(run_manifest_path)


if __name__ == "__main__":
    main()
