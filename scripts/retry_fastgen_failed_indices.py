import argparse
import json
from pathlib import Path

from fastgen_openai_v4_generate import (
    append_jsonl,
    create_operation,
    get_operation_status,
    load_env_key,
    load_or_create_ref_cache,
    load_reference_map,
    parse_prompt_blocks,
    save_success,
)


def soften_prompt(prompt: str) -> str:
    text = str(prompt)
    replacements = {
        "child reaches toward sweets": "ambient family-shopping pressure in the aisle",
        "a child reaches toward sweets": "ambient family-shopping pressure in the aisle",
        "where a child reaches toward sweets": "amid ambient family-shopping pressure",
        "child": "young family context",
        "children": "family audience",
        "teen": "young person",
        "teens": "young people",
        "teenage": "young",
        "kid": "family shopper",
        "kids": "family shoppers",
        "black box": "opaque system",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
        text = text.replace(old.capitalize(), new.capitalize())

    text = text.replace(
        "Do not let the image become a generic person-walking shot; emphasize the surrounding system, pressure, or consequence.",
        "Keep the image documentary-like and non-confrontational; emphasize environment, retail systems, and visible consequences.",
    )
    return text


def load_indices(path: Path) -> list[int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return sorted({int(item) for item in data})
    raise RuntimeError("indices json must be a list of integers")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--refs", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--indices-json", required=True)
    parser.add_argument("--soften-indices-json")
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=120)
    args = parser.parse_args()

    prompts_path = Path(args.prompts)
    refs_path = Path(args.refs)
    workdir = Path(args.workdir)
    out_dir = workdir / "images"
    meta_dir = workdir / "meta"
    failed_path = workdir / "failed_retry.jsonl"
    success_log_path = workdir / "success_retry.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    target_indices = load_indices(Path(args.indices_json))
    soften_indices = set(load_indices(Path(args.soften_indices_json))) if args.soften_indices_json else set()
    prompt_items = {item["index"]: item for item in parse_prompt_blocks(prompts_path)}

    selected = []
    for index in target_indices:
        item = prompt_items.get(index)
        if not item:
            raise KeyError(f"Prompt block not found: {index}")
        chosen = dict(item)
        if index in soften_indices:
            chosen["prompt"] = soften_prompt(chosen["prompt"])
        selected.append(chosen)

    api_key = load_env_key()
    required_ref_ids = sorted({ref_id for item in selected for ref_id in item["refs"]})
    ref_cache = {}
    if required_ref_ids:
        ref_map = load_reference_map(refs_path)
        filtered_ref_map = {ref_id: ref_map[ref_id] for ref_id in required_ref_ids}
        ref_cache = load_or_create_ref_cache(api_key, filtered_ref_map, workdir / "ref_cache.json")

    run_summary = {"done": 0, "failed": 0, "skipped": 0}
    retry_manifest = []
    for item in selected:
        output = f"{item['index']:03d}.png"
        target_path = out_dir / output
        retry_manifest.append({"index": item["index"], "refs": item["refs"], "output": output})
        if target_path.exists():
            run_summary["skipped"] += 1
            print(f"skip {item['index']:03d}")
            continue

        try:
            ref_hashes = [ref_cache[ref_id]["file_hash"] for ref_id in item["refs"]]
            created = create_operation(api_key, item["prompt"], ref_hashes, args.size)
            operation_id = created["operation_id"]

            poll_count = 0
            while True:
                status = get_operation_status(api_key, operation_id)
                poll_count += 1
                if status["status"] == "success":
                    save_success(
                        item={
                            "index": item["index"],
                            "refs": item["refs"],
                            "operation_id": operation_id,
                            "target_path": str(target_path),
                        },
                        status=status,
                        target_path=target_path,
                        meta_dir=meta_dir,
                        success_log_path=success_log_path,
                        run_summary=run_summary,
                    )
                    break
                if status["status"] == "error":
                    raise RuntimeError(json.dumps(status, ensure_ascii=False))
                if poll_count >= args.max_polls:
                    raise TimeoutError(f"Operation polling timed out: {operation_id}")
                import time
                time.sleep(args.poll_seconds)
        except Exception as exc:
            append_jsonl(
                failed_path,
                {
                    "index": item["index"],
                    "refs": item["refs"],
                    "output": output,
                    "error": str(exc),
                },
            )
            run_summary["failed"] += 1
            print(f"failed {item['index']:03d}: {exc}")

    (workdir / "retry_manifest.json").write_text(json.dumps(retry_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / "retry_run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
