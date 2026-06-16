import argparse
import json
import time
from collections import deque
from pathlib import Path

from fastgen_openai_v4_generate import (
    append_jsonl,
    create_operation,
    get_operation_status,
    iso_now,
    load_env_key,
    write_data_uri_image,
)
from project_pipeline_utils import append_event, append_log, load_json, load_project, save_json, save_project


def mark_success(item: dict, result: str, manifest: list[dict]) -> None:
    manifest.append(
        {
            "reference_asset_id": item["reference_asset_id"],
            "subject_id": item["subject_id"],
            "shot_kind": item["shot_kind"],
            "output_path": item["output_path"],
            "status": "generated",
            "operation_id": item["operation_id"],
            "timestamp": iso_now(),
            "result": result,
        }
    )


def mark_failure(item: dict, exc: Exception, manifest: list[dict], failed_path: Path) -> None:
    record = {
        "reference_asset_id": item["reference_asset_id"],
        "subject_id": item["subject_id"],
        "shot_kind": item["shot_kind"],
        "output_path": item["output_path"],
        "status": "failed",
        "timestamp": iso_now(),
        "error": str(exc),
    }
    manifest.append(record)
    append_jsonl(failed_path, record)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--size", default="1024x1536")
    parser.add_argument("--aspect-ratio", default="2:3")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    pack_path = Path(project["prompts"]["reference_prompt_pack_path"])
    manifest_path = Path(project["prompts"]["reference_generation_manifest_path"])
    workdir = Path(project["assets"]["reference_generation_run_root"])
    failed_path = workdir / "failed.jsonl"
    workdir.mkdir(parents=True, exist_ok=True)

    pack = load_json(pack_path) if pack_path.exists() else {"items": []}
    items = list(pack.get("items", []))
    for item in items:
        Path(item["output_path"]).parent.mkdir(parents=True, exist_ok=True)

    append_log(project, f"Starting reference generation in {workdir}")
    append_event(project, {"kind": "stage_start", "stage": "generate_reference_images", "count": len(items)})
    api_key = ""
    if items:
        api_key = load_env_key()

    completed_manifest: list[dict] = []
    pending = deque()
    for item in items:
        target_path = Path(item["output_path"])
        if target_path.exists():
            completed_manifest.append(
                {
                    "reference_asset_id": item["reference_asset_id"],
                    "subject_id": item["subject_id"],
                    "shot_kind": item["shot_kind"],
                    "output_path": item["output_path"],
                    "status": "existing",
                    "timestamp": iso_now(),
                }
            )
            continue
        pending.append(item)

    active: dict[str, dict] = {}
    while pending or active:
        while pending and len(active) < max(1, args.concurrency):
            item = pending.popleft()
            created = create_operation(api_key, item["prompt"], [], args.size, args.aspect_ratio)
            item["operation_id"] = created["operation_id"]
            item["poll_count"] = 0
            active[item["operation_id"]] = item

        if not active:
            continue

        finished_ops: list[str] = []
        for op_id, item in list(active.items()):
            try:
                status = get_operation_status(api_key, op_id)
                item["poll_count"] += 1
                if status["status"] == "success":
                    result = status["result"][0]
                    write_data_uri_image(result, Path(item["output_path"]))
                    mark_success(item, result[:64], completed_manifest)
                    finished_ops.append(op_id)
                elif status["status"] == "error":
                    raise RuntimeError(json.dumps(status, ensure_ascii=False))
                elif item["poll_count"] >= args.max_polls:
                    raise TimeoutError(f"Operation polling timed out: {op_id}")
            except Exception as exc:
                mark_failure(item, exc, completed_manifest, failed_path)
                finished_ops.append(op_id)

        for op_id in finished_ops:
            active.pop(op_id, None)

        if active:
            time.sleep(args.poll_seconds)

    save_json(manifest_path, {"project_id": project["project_id"], "items": completed_manifest})
    failures = [item for item in completed_manifest if item["status"] == "failed"]
    project["planning"]["status"] = "reference_images_failed" if failures else "reference_images_generated"
    project["current_stage"] = "build_subject_registry"
    save_project(project_json, project)
    append_event(
        project,
        {
            "kind": "stage_end",
            "stage": "generate_reference_images",
            "status": "failed" if failures else "completed",
            "failed_count": len(failures),
        },
    )
    append_log(project, f"Reference generation completed with {len(failures)} failures")
    print(manifest_path)


if __name__ == "__main__":
    main()
