import argparse
import json
import subprocess
import sys
from pathlib import Path

from llm_pipeline_contracts import build_generation_job_id, classify_generation_error, compute_prompt_hash, inspect_image_file, iso_now
from pipeline_contracts import stable_hash
from project_pipeline_utils import append_event, append_log, load_json, load_project, mark_stage, save_json, save_project


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--retry-rounds", type=int, default=3)
    parser.add_argument("--soften-policy-prompts", action="store_true")
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

    append_log(project, f"Starting FastGen generation in {workdir}")
    append_event(project, {"kind": "stage_start", "stage": "generate_images"})
    mark_stage(project, "generate_images", "running", current_stage="generate_images")
    save_project(project_json, project)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "fastgen_openai_v4_generate.py"),
        "--prompts",
        str(prompt_file),
        "--refs",
        project["prompts"]["reference_mapping_path"],
        "--workdir",
        str(workdir),
        "--size",
        args.size,
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

    retry_rounds = max(1, args.retry_rounds)
    failed_path = workdir / "failed.jsonl"
    last_failed_records: list[dict] = []
    job_id = build_generation_job_id(project["project_id"])
    created_at = iso_now()

    for round_index in range(1, retry_rounds + 1):
        append_log(project, f"FastGen attempt {round_index}/{retry_rounds}")
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
    raw_manifest = load_json(run_manifest_path)
    run_summary_path = workdir / "run_summary.json"
    run_summary = load_json(run_summary_path) if run_summary_path.exists() else {"done": 0, "skipped": 0, "failed": 0}
    prompt_package = load_json(prompt_package_path)
    scene_plan = load_json(scene_plan_path)
    scene_by_prompt_index, scene_map = build_scene_lookup(prompt_file, scene_plan, prompt_package)
    failed_lookup = build_failed_lookup(last_failed_records)
    prompt_profile = {
        "provider": "fastgen_openai_v4",
        "size": args.size,
    }
    generated_images = []
    for record in raw_manifest:
        prompt_index = int(record["source_prompt_index"])
        scene_id = scene_by_prompt_index.get(prompt_index)
        if not scene_id:
            continue
        image_path = str(workdir / "images" / record["output"])
        failed_meta = failed_lookup.get(int(record["index"]))
        if Path(image_path).exists():
            status = "success"
            error_type = ""
            error_message = ""
        elif failed_meta:
            status = "failed"
            error_type = failed_meta["error_type"]
            error_message = failed_meta["error_message"]
        else:
            status = "missing"
            error_type = "filesystem_error"
            error_message = "Image file missing after generation run"
        prompt_hash = compute_prompt_hash(
            prompt=record.get("prompt", ""),
            refs=record.get("refs", []),
            settings=prompt_profile,
        )
        image_info = inspect_image_file(Path(image_path)) if status == "success" else {}
        generated_images.append(
            {
                "job_id": job_id,
                "created_at": created_at,
                "scene_id": scene_id,
                "source_prompt_index": prompt_index,
                "variant_index": int(record.get("variant_index", 1) or 1),
                "variant_label": str(record.get("variant_label", f"V{int(record.get('variant_index', 1) or 1):02d}")),
                "prompt_hash": prompt_hash,
                "generator_profile": stable_hash(prompt_profile),
                "generator_settings": prompt_profile,
                "refs": record.get("refs", []),
                "prompt": record.get("prompt", ""),
                "output_file": record["output"],
                "image_path": image_path,
                "beat_priority": record.get("beat_priority", "standard"),
                "key_beat": bool(record.get("key_beat")),
                "variant_count": int(record.get("variant_count", 1) or 1),
                "selection_required": bool(record.get("selection_required")),
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
            scene["generated_index"] = prompt_index
            scene["still_image_path"] = image_path
            scene["render_source"] = "still"
            scene["render_asset_path"] = image_path
            notes = [note for note in scene.get("notes", []) if note != "Still image pending"]
            if "Generated image ready" not in notes:
                notes.append("Generated image ready")
            scene["notes"] = notes

    enriched_manifest = {
        "project_id": project["project_id"],
        "job_id": job_id,
        "created_at": created_at,
        "profile_id": project["profile_id"],
        "prompt_file": str(prompt_file),
        "workdir": str(workdir),
        "generator_profile": prompt_profile,
        "generated_images": generated_images,
        "failed_count": int(run_summary.get("failed", 0) or 0),
        "completed_count": sum(1 for item in generated_images if item["status"] == "success"),
        "skipped_count": int(run_summary.get("skipped", 0) or 0),
        "retry_rounds_used": retry_rounds,
    }
    save_json(run_manifest_path, enriched_manifest)
    save_json(scene_plan_path, scene_plan)

    project["images"]["status"] = "generated"
    project["images"]["job_id"] = job_id
    project["images"]["generated_count"] = enriched_manifest["completed_count"]
    project["images"]["failed_count"] = enriched_manifest["failed_count"]
    project["current_stage"] = "image_qc"
    save_project(project_json, project)
    append_event(project, {"kind": "stage_end", "stage": "generate_images", "status": "generated"})
    append_log(project, f"FastGen generation completed: {enriched_manifest['completed_count']} images ready")

    print(run_manifest_path)


if __name__ == "__main__":
    main()
