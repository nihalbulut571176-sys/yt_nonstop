import argparse
import base64
from datetime import datetime, timezone
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any


ROOT = "https://googler.fast-gen.ai"
STORAGE = "https://storage.fast-gen.ai"
ENV_PATH = Path(r"C:\Users\MIKE\Documents\Codex\YT\.env")
DEFAULT_PROMPTS = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_generator_ready.md")
DEFAULT_REFS = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\fastgen_ref_paths.json")
DEFAULT_WORKDIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\fastgen_run")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return __import__("hashlib").sha256(data.encode("utf-8")).hexdigest()


def load_env_key() -> str:
    if "FAST_GEN_API_KEY" in os.environ and os.environ["FAST_GEN_API_KEY"].strip():
        return os.environ["FAST_GEN_API_KEY"].strip()
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("FAST_GEN_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("FAST_GEN_API_KEY not found in .env")


def request_json(url: str, method: str = "GET", headers=None, data=None):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_json_with_retries(url: str, method: str = "GET", headers=None, data=None, attempts: int = 3, sleep_seconds: float = 5.0):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return request_json(url, method=method, headers=headers, data=data)
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(sleep_seconds * attempt)
    assert last_error is not None
    raise last_error


def parse_prompt_blocks(path: Path):
    blocks = [block.strip() for block in path.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    parsed = []
    for index, block in enumerate(blocks, start=1):
        if block.startswith("No character reference. "):
            parsed.append(
                {
                    "index": index,
                    "refs": [],
                    "prompt": block[len("No character reference. ") :].strip(),
                }
            )
            continue

        multi = re.match(r"Use reference images:\s+([A-Za-z0-9_,\s]+)\.\s+(.*)$", block, re.S)
        if multi:
            refs = [item.strip() for item in multi.group(1).split(",")]
            parsed.append({"index": index, "refs": refs, "prompt": multi.group(2).strip()})
            continue

        single = re.match(r"Use reference image:\s+([A-Za-z0-9_]+)\.\s+(.*)$", block, re.S)
        if single:
            parsed.append({"index": index, "refs": [single.group(1)], "prompt": single.group(2).strip()})
            continue

        raise ValueError(f"Unrecognized prompt format at block {index}")
    return parsed


def validate_prompt_export(path: Path, parsed_blocks: list[dict]) -> None:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    prompt_count = len(parsed_blocks)
    export_text = path.read_text(encoding="utf-8")
    computed_signature = stable_hash(
        {
            "package_path": meta.get("package_path"),
            "package_signature": meta.get("package_signature"),
            "prompt_count": prompt_count,
            "content": export_text,
        }
    )
    if prompt_count != meta.get("prompt_count"):
        raise RuntimeError(f"Prompt export count mismatch for {path}: meta={meta.get('prompt_count')} actual={prompt_count}")
    if computed_signature != meta.get("export_signature"):
        raise RuntimeError(f"Prompt export signature mismatch for {path}; rebuild export before generation")


def load_export_meta(path: Path) -> dict[str, Any]:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_reference_map(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f"Reference mapping not found: {path}. Copy fastgen_ref_paths.template.json to fastgen_ref_paths.json and fill real paths."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: Path(value) for key, value in data.items()}


def build_multipart(file_path: Path, boundary: str):
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    content = file_path.read_bytes()
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return header + content + footer


def upload_reference(api_key: str, file_path: Path) -> str:
    boundary = f"----FASTGENBOUNDARY{int(time.time() * 1000)}"
    body = build_multipart(file_path, boundary)
    headers = {
        "X-API-Key": api_key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    result = request_json_with_retries(f"{STORAGE}/upload", method="POST", headers=headers, data=body)
    return result["file_hash"]


def load_or_create_ref_cache(api_key: str, ref_map: dict, cache_path: Path):
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        cache = {}

    changed = False
    for ref_id, file_path in ref_map.items():
        if ref_id in cache and cache[ref_id].get("local_path") == str(file_path):
            continue
        if not file_path.exists():
            raise FileNotFoundError(f"Reference file not found for {ref_id}: {file_path}")
        file_hash = upload_reference(api_key, file_path)
        cache[ref_id] = {"local_path": str(file_path), "file_hash": file_hash}
        changed = True

    if changed or not cache_path.exists():
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache


def create_operation(api_key: str, prompt: str, refs: list[str], size: str, aspect_ratio: str):
    payload = {"prompt": prompt, "size": size, "aspect_ratio": aspect_ratio}
    if refs:
        payload["reference_images"] = refs
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8")
    return request_json_with_retries(f"{ROOT}/api/v4/openai/image/generate", method="POST", headers=headers, data=data)


def poll_operation(api_key: str, operation_id: str, poll_seconds: float = 3.0, max_polls: int = 120):
    headers = {"X-API-Key": api_key}
    for _ in range(max_polls):
        status = request_json_with_retries(f"{ROOT}/api/v4/operations/{operation_id}", method="GET", headers=headers)
        if status["status"] == "success":
            return status
        if status["status"] == "error":
            raise RuntimeError(json.dumps(status, ensure_ascii=False))
        time.sleep(poll_seconds)
    raise TimeoutError(f"Operation polling timed out: {operation_id}")


def get_operation_status(api_key: str, operation_id: str):
    headers = {"X-API-Key": api_key}
    return request_json_with_retries(f"{ROOT}/api/v4/operations/{operation_id}", method="GET", headers=headers)


def write_data_uri_image(data_uri: str, target_path: Path):
    if not data_uri.startswith("data:image/"):
        raise ValueError("Unexpected result format: not an image data URI")
    header, b64 = data_uri.split(",", 1)
    target_path.write_bytes(base64.b64decode(b64))


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def append_live_log(text_path: Path, jsonl_path: Path, event: dict[str, Any]) -> None:
    line = f"[{event['timestamp']}] {event['level']} {event['event']}"
    details = event.get("details")
    if details:
        line += f" | {details}"
    with text_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    append_jsonl(jsonl_path, event)


def is_policy_error(exc: Exception | str) -> bool:
    message = str(exc).lower()
    markers = (
        "content polic",
        "may violate our content policies",
        "guardrails around violence",
        "violence",
        "rejected by openai content policy",
    )
    return any(marker in message for marker in markers)


def mark_failed(
    item: dict[str, Any],
    exc: Exception,
    failed_path: Path,
    run_summary: dict[str, int],
    live_log_path: Path,
    live_jsonl_path: Path,
) -> None:
    failure = {
        "index": item["index"],
        "refs": item["refs"],
        "output": item["output"],
        "error": str(exc),
    }
    append_jsonl(failed_path, failure)
    run_summary["failed"] += 1
    append_live_log(
        live_log_path,
        live_jsonl_path,
        {
            "timestamp": iso_now(),
            "level": "ERROR",
            "event": f"failed_{item['index']:03d}",
            "details": str(exc),
            "index": item["index"],
            "output": item["output"],
            "refs": item["refs"],
        },
    )
    print(f"failed {item['index']:03d}: {exc}")


def save_success(
    item: dict[str, Any],
    status: dict[str, Any],
    target_path: Path,
    meta_dir: Path,
    success_log_path: Path,
    run_summary: dict[str, int],
    live_log_path: Path,
    live_jsonl_path: Path,
) -> None:
    result = status["result"]
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"Unexpected result payload for {item['index']:03d}: {json.dumps(status, ensure_ascii=False)}")
    write_data_uri_image(result[0], target_path)

    meta_record = {
        "index": item["index"],
        "scene_id": item["scene_id"],
        "variant_index": item["variant_index"],
        "beat_priority": item["beat_priority"],
        "refs": item["refs"],
        "operation_id": item["operation_id"],
        "status": status["status"],
        "provider": status.get("provider"),
        "output_file": str(target_path),
    }
    meta_path = meta_dir / f"{item['index']:03d}.json"
    meta_path.write_text(json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8")
    append_jsonl(success_log_path, meta_record)
    run_summary["done"] += 1
    append_live_log(
        live_log_path,
        live_jsonl_path,
        {
            "timestamp": iso_now(),
            "level": "INFO",
            "event": f"done_{item['index']:03d}",
            "details": str(target_path),
            "index": item["index"],
            "scene_id": item["scene_id"],
            "refs": item["refs"],
        },
    )
    print(f"done {item['index']:03d}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS))
    parser.add_argument("--refs", default=str(DEFAULT_REFS))
    parser.add_argument("--workdir", default=str(DEFAULT_WORKDIR))
    parser.add_argument("--size", default="1920x1080")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--index-offset", type=int, default=0)
    parser.add_argument("--images-dir", default="")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--max-consecutive-failures", type=int, default=5)
    args = parser.parse_args()

    prompts_path = Path(args.prompts)
    refs_path = Path(args.refs)
    workdir = Path(args.workdir)
    out_dir = Path(args.images_dir) if args.images_dir else workdir / "images"
    meta_dir = workdir / "meta"
    failed_path = workdir / "failed.jsonl"
    success_log_path = workdir / "success.jsonl"
    live_log_path = workdir / "live_generation.log"
    live_jsonl_path = workdir / "live_generation.jsonl"
    fatal_report_path = workdir / "fatal_consecutive_failures_report.json"
    workdir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    api_key = load_env_key()
    prompt_items = parse_prompt_blocks(prompts_path)
    validate_prompt_export(prompts_path, prompt_items)
    export_meta = load_export_meta(prompts_path)
    end = args.end if args.end > 0 else len(prompt_items)
    prompt_items = [item for item in prompt_items if args.start <= item["index"] <= end]

    ref_map = load_reference_map(refs_path)
    ref_cache = load_or_create_ref_cache(api_key, ref_map, workdir / "ref_cache.json")

    package_items = {item["scene_id"]: item for item in export_meta.get("package_items", []) if item.get("scene_id")}
    manifest = []
    for item in prompt_items:
        prompt_meta = export_meta.get("package_items", [])
        prompt_item_meta = prompt_meta[item["index"] - 1] if item["index"] - 1 < len(prompt_meta) else {}
        scene_id = prompt_item_meta.get("scene_id", f"scene_{item['index']:04d}")
        variant_count = max(1, int(prompt_item_meta.get("variant_count", 1) or 1))
        for variant_index in range(1, variant_count + 1):
            output_index = args.index_offset + len(manifest) + 1
            manifest.append(
                {
                    "index": output_index,
                    "scene_id": scene_id,
                    "variant_index": variant_index,
                    "variant_label": f"V{variant_index:02d}",
                    "source_prompt_index": item["index"],
                    "beat_priority": prompt_item_meta.get("beat_priority", "standard"),
                    "key_beat": bool(prompt_item_meta.get("key_beat")),
                    "variant_count": variant_count,
                    "refs": item["refs"],
                    "prompt": item["prompt"],
                    "output": f"{scene_id}_V{variant_index:02d}.png",
                    "selection_required": bool(prompt_item_meta.get("key_beat")) or variant_count > 1,
                }
            )
    (workdir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    append_live_log(
        live_log_path,
        live_jsonl_path,
        {
            "timestamp": iso_now(),
            "level": "INFO",
            "event": "run_started",
            "details": f"manifest_items={len(manifest)} concurrency={args.concurrency}",
        },
    )

    run_summary = {"done": 0, "skipped": 0, "failed": 0}
    consecutive_failures = 0
    recent_failures: list[dict[str, Any]] = []
    pending = deque()
    for item in manifest:
        target_path = out_dir / item["output"]
        if target_path.exists():
            print(f"skip {item['index']:03d}")
            run_summary["skipped"] += 1
            append_live_log(
                live_log_path,
                live_jsonl_path,
                {
                    "timestamp": iso_now(),
                    "level": "INFO",
                    "event": f"skip_{item['index']:03d}",
                    "details": str(target_path),
                    "index": item["index"],
                },
            )
            continue
        pending.append(item)

    active: dict[str, dict[str, Any]] = {}

    while pending or active:
        while pending and len(active) < max(1, args.concurrency):
            item = pending.popleft()
            target_path = out_dir / item["output"]
            try:
                ref_hashes = [ref_cache[ref_id]["file_hash"] for ref_id in item["refs"]]
                created = create_operation(api_key, item["prompt"], ref_hashes, args.size, args.aspect_ratio)
                op_id = created["operation_id"]
                item["operation_id"] = op_id
                item["target_path"] = str(target_path)
                item["poll_count"] = 0
                active[op_id] = item
                append_live_log(
                    live_log_path,
                    live_jsonl_path,
                    {
                        "timestamp": iso_now(),
                        "level": "INFO",
                        "event": f"queued_{item['index']:03d}",
                        "details": op_id,
                        "index": item["index"],
                        "refs": item["refs"],
                    },
                )
                print(f"queued {item['index']:03d} -> {op_id}")
            except Exception as exc:
                mark_failed(item, exc, failed_path, run_summary, live_log_path, live_jsonl_path)
                if not is_policy_error(exc):
                    consecutive_failures += 1
                    recent_failures.append({"index": item["index"], "stage": "queue", "error": str(exc)})
                    recent_failures = recent_failures[-args.max_consecutive_failures :]
                    if consecutive_failures >= args.max_consecutive_failures:
                        fatal_payload = {
                            "timestamp": iso_now(),
                            "reason": "max_consecutive_failures_reached",
                            "threshold": args.max_consecutive_failures,
                            "recent_failures": recent_failures,
                        }
                        fatal_report_path.write_text(json.dumps(fatal_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                        append_live_log(
                            live_log_path,
                            live_jsonl_path,
                            {
                                "timestamp": iso_now(),
                                "level": "FATAL",
                                "event": "run_aborted_consecutive_failures",
                                "details": json.dumps(fatal_payload, ensure_ascii=False),
                            },
                        )
                        raise RuntimeError(f"Aborted after {args.max_consecutive_failures} consecutive failures. See {fatal_report_path}")
                if args.stop_on_error:
                    raise

        if not active:
            continue

        finished_ops: list[str] = []
        for op_id, item in list(active.items()):
            try:
                status = get_operation_status(api_key, op_id)
                item["poll_count"] += 1
                if status["status"] == "success":
                    save_success(
                        item=item,
                        status=status,
                        target_path=Path(item["target_path"]),
                        meta_dir=meta_dir,
                        success_log_path=success_log_path,
                        run_summary=run_summary,
                        live_log_path=live_log_path,
                        live_jsonl_path=live_jsonl_path,
                    )
                    consecutive_failures = 0
                    finished_ops.append(op_id)
                elif status["status"] == "error":
                    raise RuntimeError(json.dumps(status, ensure_ascii=False))
                elif item["poll_count"] >= args.max_polls:
                    raise TimeoutError(f"Operation polling timed out: {op_id}")
            except Exception as exc:
                mark_failed(item, exc, failed_path, run_summary, live_log_path, live_jsonl_path)
                if not is_policy_error(exc):
                    consecutive_failures += 1
                    recent_failures.append({"index": item["index"], "stage": "poll", "error": str(exc)})
                    recent_failures = recent_failures[-args.max_consecutive_failures :]
                finished_ops.append(op_id)
                if not is_policy_error(exc) and consecutive_failures >= args.max_consecutive_failures:
                    fatal_payload = {
                        "timestamp": iso_now(),
                        "reason": "max_consecutive_failures_reached",
                        "threshold": args.max_consecutive_failures,
                        "recent_failures": recent_failures,
                    }
                    fatal_report_path.write_text(json.dumps(fatal_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    append_live_log(
                        live_log_path,
                        live_jsonl_path,
                        {
                            "timestamp": iso_now(),
                            "level": "FATAL",
                            "event": "run_aborted_consecutive_failures",
                            "details": json.dumps(fatal_payload, ensure_ascii=False),
                        },
                    )
                    raise RuntimeError(f"Aborted after {args.max_consecutive_failures} consecutive failures. See {fatal_report_path}")
                if args.stop_on_error:
                    raise

        for op_id in finished_ops:
            active.pop(op_id, None)

        if active:
            time.sleep(args.poll_seconds)

    generation_report_path = workdir / "generation_report.md"
    generation_report_lines = [
        "# Generation Report",
        "",
        f"Prompt source: {prompts_path}",
        f"Manifest items: {len(manifest)}",
        f"Aspect ratio: {args.aspect_ratio}",
        f"Size: {args.size}",
        f"Generated: {run_summary['done']}",
        f"Skipped: {run_summary['skipped']}",
        f"Failed: {run_summary['failed']}",
        f"Realtime log: {live_log_path}",
        f"Realtime JSONL: {live_jsonl_path}",
        f"Max consecutive failures: {args.max_consecutive_failures}",
    ]
    (workdir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    generation_report_path.write_text("\n".join(generation_report_lines) + "\n", encoding="utf-8")
    append_live_log(
        live_log_path,
        live_jsonl_path,
        {
            "timestamp": iso_now(),
            "level": "INFO",
            "event": "run_finished",
            "details": json.dumps(run_summary, ensure_ascii=False),
        },
    )
    print(json.dumps(run_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
