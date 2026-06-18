from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for candidate in (SRC, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from llm_pipeline_contracts import compute_prompt_hash, inspect_image_file, iso_now
from project_pipeline_utils import append_event, append_log, load_json, load_project, save_json, save_project


ENV_PATHS = [ROOT / ".env", Path(r"C:\Users\MIKE\Documents\Codex\YT_visual\.env")]
BASE_URL = "https://veononstop.org/api/v1"
DEFAULT_MODEL_KEY = "GEM_PIX_2"


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def load_env_value(key: str) -> str:
    value = clean_text(os.environ.get(key))
    if value:
        return value
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            env_key, env_value = line.split("=", 1)
            if env_key.strip() == key and clean_text(env_value):
                return clean_text(env_value)
    return ""


def request_json(url: str, *, api_key: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"VeoNonStop returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"VeoNonStop request failed: {exc.reason}") from exc


def download_url(url: str, target_path: Path, *, timeout: int = 180) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "yt_nonstop/veononstop-image-runner"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(response.read())


def load_generation_items(project: dict[str, Any], *, limit_frames: int) -> list[dict[str, Any]]:
    batches_path = Path(project["prompts"]["fastgen_export_path"]).with_suffix(".batches.json")
    if not batches_path.exists():
        raise FileNotFoundError(f"Generation batches not found: {batches_path}")
    rows = load_json(batches_path)
    if not isinstance(rows, list):
        raise RuntimeError("Generation batches must be a list")
    selected = rows[: max(0, int(limit_frames or 0)) or None]
    workdir = Path(project["images"]["run_manifest_path"]).parent
    output_dir = workdir / "images"
    result = []
    for row in selected:
        if not row.get("frame_id") or not row.get("generator_prompt"):
            continue
        scene_id = str(row.get("scene_id") or row.get("visual_slot_id") or row.get("frame_id"))
        if (output_dir / f"{scene_id}_V01.png").exists():
            continue
        result.append(row)
    return result


def load_all_generation_rows(project: dict[str, Any], *, limit_frames: int) -> list[dict[str, Any]]:
    batches_path = Path(project["prompts"]["fastgen_export_path"]).with_suffix(".batches.json")
    rows = load_json(batches_path)
    if not isinstance(rows, list):
        raise RuntimeError("Generation batches must be a list")
    selected = rows[: max(0, int(limit_frames or 0)) or None]
    return [row for row in selected if row.get("frame_id") and row.get("generator_prompt")]


def generate_one(
    *,
    api_key: str,
    row: dict[str, Any],
    output_dir: Path,
    aspect_ratio: str,
    model_key: str,
) -> dict[str, Any]:
    frame_id = str(row["frame_id"])
    scene_id = str(row.get("scene_id") or row.get("visual_slot_id") or frame_id)
    prompt = clean_text(row.get("generator_prompt") or row.get("image_prompt") or "")
    negative_prompt = clean_text(row.get("negative_prompt"))
    full_prompt = prompt if not negative_prompt else f"{prompt}\n\nNegative prompt: {negative_prompt}"
    target_path = output_dir / f"{scene_id}_V01.png"
    payload = {
        "prompt": full_prompt,
        "num_images": 1,
        "aspect_ratio": aspect_ratio,
        "model_key": model_key,
    }
    started_at = iso_now()
    response = request_json(f"{BASE_URL}/image/banana/generate", api_key=api_key, payload=payload)
    if not response.get("success"):
        raise RuntimeError(json.dumps(response, ensure_ascii=False))
    media = (response.get("data") or {}).get("media") or []
    if not media:
        raise RuntimeError(f"VeoNonStop response has no media for {frame_id}")
    first = media[0]
    fife_url = first.get("fifeUrl")
    if not fife_url:
        raise RuntimeError(f"VeoNonStop response has no fifeUrl for {frame_id}")
    download_url(str(fife_url), target_path)
    inspection = inspect_image_file(target_path)
    return {
        "scene_id": scene_id,
        "frame_id": frame_id,
        "beat_id": row.get("beat_id", ""),
        "visual_slot_id": row.get("visual_slot_id", scene_id),
        "variant_index": 1,
        "variant_label": "V01",
        "variant_count": int(row.get("variant_count", 1) or 1),
        "status": "success",
        "provider": "veononstop_banana",
        "model": model_key,
        "provider_job_id": str(first.get("mediaGenerationId") or first.get("mediaName") or ""),
        "media_generation_id": str(first.get("mediaGenerationId") or ""),
        "source_url": str(fife_url),
        "image_path": str(target_path),
        "prompt_hash": compute_prompt_hash(full_prompt),
        "prompt": full_prompt,
        "started_at": started_at,
        "finished_at": iso_now(),
        "image_info": inspection,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--limit-frames", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    api_key = load_env_value("VEO_NONSTOP_API_KEY")
    if not api_key:
        raise RuntimeError("VEO_NONSTOP_API_KEY is missing in environment or .env")

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    workdir = Path(project["images"]["run_manifest_path"]).parent
    output_dir = workdir / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path = Path(project["images"]["run_manifest_path"])
    all_rows = load_all_generation_rows(project, limit_frames=int(args.limit_frames or 0))
    rows = load_generation_items(project, limit_frames=int(args.limit_frames or 0))
    if not all_rows:
        raise RuntimeError("No generation rows selected")

    append_log(project, f"Starting VeoNonStop Banana image generation in {output_dir}; selected={len(rows)}")
    append_event(project, {"kind": "stage_start", "stage": "generate_images", "provider": "veononstop_banana", "selected": len(rows)})
    project["images"]["status"] = "running"
    project["images"]["provider"] = "VeoNonStop Banana"
    project["images"]["route"] = "image/banana/generate"
    project["images"]["limit_frames"] = len(rows)
    project["current_stage"] = "generate_images"
    save_project(project_json, project)

    generated: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    started_at = iso_now()
    max_workers = max(1, min(int(args.concurrency or 1), 4))
    if rows:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    generate_one,
                    api_key=api_key,
                    row=row,
                    output_dir=output_dir,
                    aspect_ratio=args.aspect_ratio,
                    model_key=args.model_key,
                ): row
                for row in rows
            }
            for future in as_completed(futures):
                row = futures[future]
                try:
                    record = future.result()
                    generated.append(record)
                    print(f"OK {record['frame_id']} -> {record['image_path']}", flush=True)
                except Exception as exc:
                    failure = {
                        "scene_id": row.get("scene_id") or row.get("visual_slot_id") or row.get("frame_id"),
                        "frame_id": row.get("frame_id"),
                        "beat_id": row.get("beat_id", ""),
                        "status": "failed",
                        "provider": "veononstop_banana",
                        "error": str(exc),
                        "finished_at": iso_now(),
                    }
                    failed.append(failure)
                    print(f"FAIL {failure['frame_id']}: {failure['error']}", flush=True)
                    if args.stop_on_error:
                        break

    generated_by_frame = {item["frame_id"]: item for item in generated if item.get("status") == "success"}
    for row in all_rows:
        frame_id = str(row["frame_id"])
        if frame_id in generated_by_frame:
            continue
        scene_id = str(row.get("scene_id") or row.get("visual_slot_id") or frame_id)
        existing_path = output_dir / f"{scene_id}_V01.png"
        if existing_path.exists():
            generated_by_frame[frame_id] = {
                "scene_id": scene_id,
                "frame_id": frame_id,
                "beat_id": row.get("beat_id", ""),
                "visual_slot_id": row.get("visual_slot_id", scene_id),
                "variant_index": 1,
                "variant_label": "V01",
                "variant_count": int(row.get("variant_count", 1) or 1),
                "status": "success",
                "provider": "veononstop_banana",
                "model": args.model_key,
                "provider_job_id": "",
                "media_generation_id": "",
                "source_url": "",
                "image_path": str(existing_path),
                "prompt_hash": compute_prompt_hash(clean_text(row.get("generator_prompt"))),
                "prompt": clean_text(row.get("generator_prompt")),
                "started_at": started_at,
                "finished_at": iso_now(),
                "image_info": inspect_image_file(existing_path),
            }

    generated = list(generated_by_frame.values())

    generated_sorted = sorted(generated + failed, key=lambda item: str(item.get("frame_id") or item.get("scene_id") or ""))
    completed_count = sum(1 for item in generated_sorted if item.get("status") == "success")
    failed_count = sum(1 for item in generated_sorted if item.get("status") == "failed")
    manifest = {
        "project_id": project["project_id"],
        "provider": "veononstop_banana",
        "route": "image/banana/generate",
        "model_key": args.model_key,
        "real_generation": True,
        "limited_pilot": True,
        "partial_pilot": failed_count > 0 or completed_count < len(rows),
        "limit_frames": len(all_rows),
        "planned_generative_frames_count": len(all_rows),
        "generated_count": completed_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "missing_count": 0,
        "started_at": started_at,
        "finished_at": iso_now(),
        "generated_images": generated_sorted,
    }
    save_json(run_manifest_path, manifest)

    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    if final_scene_plan_path.exists():
        scene_plan = load_json(final_scene_plan_path)
        by_scene = {item.get("scene_id"): item for item in generated_sorted if item.get("status") == "success"}
        for scene in scene_plan.get("scenes", []):
            hit = by_scene.get(scene.get("scene_id"))
            if hit:
                scene["still_image_path"] = hit["image_path"]
                scene["render_asset_path"] = hit["image_path"]
        save_json(final_scene_plan_path, scene_plan)

    project = load_project(project_json)
    project["images"]["provider"] = "VeoNonStop Banana"
    project["images"]["route"] = "image/banana/generate"
    project["images"]["status"] = "generated" if failed_count == 0 else "partial"
    project["images"]["generated_count"] = completed_count
    project["images"]["failed_count"] = failed_count
    project["images"]["missing_count"] = 0
    project["images"]["limit_frames"] = len(all_rows)
    project["current_stage"] = "image_qc" if failed_count == 0 else "generate_images"
    save_project(project_json, project)
    append_event(project, {"kind": "stage_end", "stage": "generate_images", "provider": "veononstop_banana", "completed": completed_count, "failed": failed_count})
    append_log(project, f"VeoNonStop image generation completed: {completed_count} ready; failed={failed_count}")
    print(run_manifest_path)


if __name__ == "__main__":
    main()
