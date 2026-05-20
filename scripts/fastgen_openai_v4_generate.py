import argparse
import base64
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


def create_operation(api_key: str, prompt: str, refs: list[str], size: str):
    payload = {"prompt": prompt, "size": size}
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


def mark_failed(
    item: dict[str, Any],
    exc: Exception,
    failed_path: Path,
    run_summary: dict[str, int],
) -> None:
    failure = {
        "index": item["index"],
        "refs": item["refs"],
        "output": item["output"],
        "error": str(exc),
    }
    append_jsonl(failed_path, failure)
    run_summary["failed"] += 1
    print(f"failed {item['index']:03d}: {exc}")


def save_success(
    item: dict[str, Any],
    status: dict[str, Any],
    target_path: Path,
    meta_dir: Path,
    success_log_path: Path,
    run_summary: dict[str, int],
) -> None:
    result = status["result"]
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"Unexpected result payload for {item['index']:03d}: {json.dumps(status, ensure_ascii=False)}")
    write_data_uri_image(result[0], target_path)

    meta_record = {
        "index": item["index"],
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
    print(f"done {item['index']:03d}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS))
    parser.add_argument("--refs", default=str(DEFAULT_REFS))
    parser.add_argument("--workdir", default=str(DEFAULT_WORKDIR))
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--index-offset", type=int, default=0)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    prompts_path = Path(args.prompts)
    refs_path = Path(args.refs)
    workdir = Path(args.workdir)
    out_dir = workdir / "images"
    meta_dir = workdir / "meta"
    failed_path = workdir / "failed.jsonl"
    success_log_path = workdir / "success.jsonl"
    workdir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    api_key = load_env_key()
    prompt_items = parse_prompt_blocks(prompts_path)
    end = args.end if args.end > 0 else len(prompt_items)
    prompt_items = [item for item in prompt_items if args.start <= item["index"] <= end]

    ref_map = load_reference_map(refs_path)
    ref_cache = load_or_create_ref_cache(api_key, ref_map, workdir / "ref_cache.json")

    manifest = []
    for item in prompt_items:
        output_index = args.index_offset + item["index"]
        manifest.append(
            {
                "index": output_index,
                "source_prompt_index": item["index"],
                "refs": item["refs"],
                "prompt": item["prompt"],
                "output": f"{output_index:03d}.png",
            }
        )
    (workdir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    run_summary = {"done": 0, "skipped": 0, "failed": 0}
    pending = deque()
    for item in manifest:
        target_path = out_dir / item["output"]
        if target_path.exists():
            print(f"skip {item['index']:03d}")
            run_summary["skipped"] += 1
            continue
        pending.append(item)

    active: dict[str, dict[str, Any]] = {}

    while pending or active:
        while pending and len(active) < max(1, args.concurrency):
            item = pending.popleft()
            target_path = out_dir / item["output"]
            try:
                ref_hashes = [ref_cache[ref_id]["file_hash"] for ref_id in item["refs"]]
                created = create_operation(api_key, item["prompt"], ref_hashes, args.size)
                op_id = created["operation_id"]
                item["operation_id"] = op_id
                item["target_path"] = str(target_path)
                item["poll_count"] = 0
                active[op_id] = item
                print(f"queued {item['index']:03d} -> {op_id}")
            except Exception as exc:
                mark_failed(item, exc, failed_path, run_summary)
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
                    )
                    finished_ops.append(op_id)
                elif status["status"] == "error":
                    raise RuntimeError(json.dumps(status, ensure_ascii=False))
                elif item["poll_count"] >= args.max_polls:
                    raise TimeoutError(f"Operation polling timed out: {op_id}")
            except Exception as exc:
                mark_failed(item, exc, failed_path, run_summary)
                finished_ops.append(op_id)
                if args.stop_on_error:
                    raise

        for op_id in finished_ops:
            active.pop(op_id, None)

        if active:
            time.sleep(args.poll_seconds)

    (workdir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
