import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return __import__("hashlib").sha256(data.encode("utf-8")).hexdigest()


def build_block(prompt: str, negative: str) -> str:
    prompt = " ".join((prompt or "").split())
    negative = " ".join((negative or "").split())
    full_prompt = prompt
    if negative:
        full_prompt = f"{prompt} Negative prompt: {negative}".strip()
    return f"No character reference. {full_prompt}".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--project-id", default="deshevaya_eda_001")
    parser.add_argument("--prompt-column", default="")
    parser.add_argument("--negative-column", default="")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    output_path = Path(args.output).resolve()
    meta_path = output_path.with_suffix(output_path.suffix + ".meta.json")

    with csv_path.open("r", encoding=args.encoding, newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    fieldnames = reader.fieldnames or []
    prompt_column = args.prompt_column or (
        "image_prompt_genlock_ru"
        if "image_prompt_genlock_ru" in fieldnames
        else "image_prompt_rewritten_v2_3"
        if "image_prompt_rewritten_v2_3" in fieldnames
        else ""
    )
    negative_column = args.negative_column or (
        "negative_prompt_genlock"
        if "negative_prompt_genlock" in fieldnames
        else "negative_prompt_rewritten_v2_3"
        if "negative_prompt_rewritten_v2_3" in fieldnames
        else ""
    )

    if not prompt_column or prompt_column not in fieldnames:
        raise RuntimeError(f"Prompt column not found in CSV. Available columns: {fieldnames}")

    blocks = []
    package_items = []
    for index, row in enumerate(rows, start=1):
        frame_id = (row.get("frame_id") or f"frame_{index:04d}").strip()
        prompt = row.get(prompt_column, "")
        negative = row.get(negative_column, "") if negative_column else ""
        block = build_block(prompt, negative)
        blocks.append(block)
        package_items.append(
            {
                "scene_id": frame_id,
                "beat_priority": row.get("priority", "standard"),
                "key_beat": (row.get("priority", "") or "").strip().lower() in {"обязательный", "опорный", "must_land"},
                "variant_count": 1,
                "reference_ids": [],
                "frame_id": frame_id,
                "segment_id": row.get("segment_id", ""),
                "scene_title": row.get("scene_title", ""),
                "frame_timecode_exact": row.get("frame_timecode_exact", ""),
                "generation_lock_status": row.get("generation_lock_status", ""),
                "prompt_column": prompt_column,
                "negative_column": negative_column,
            }
        )

    export_text = "\n\n".join(blocks).strip() + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(export_text, encoding="utf-8")

    export_signature = stable_hash(
        {
            "package_path": str(csv_path),
            "package_signature": stable_hash({"csv_path": str(csv_path), "row_count": len(rows), "items": package_items}),
            "prompt_count": len(blocks),
            "content": export_text,
        }
    )

    meta = {
        "generated_at": iso_now(),
        "project_id": args.project_id,
        "package_path": str(csv_path),
        "package_signature": stable_hash({"csv_path": str(csv_path), "row_count": len(rows), "items": package_items}),
        "package_scene_count": len(rows),
        "prompt_count": len(blocks),
        "export_signature": export_signature,
        "generator_ready_path": str(output_path),
        "profile_id": "fastgen_csv_mass_run",
        "prompt_column": prompt_column,
        "negative_column": negative_column,
        "package_items": package_items,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(output_path)
    print(meta_path)
    print(len(rows))


if __name__ == "__main__":
    main()
