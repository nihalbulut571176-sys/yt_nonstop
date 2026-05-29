import argparse
import csv
import json
from pathlib import Path

from pipeline_contracts import stable_hash
from project_pipeline_utils import load_json, load_project, save_project


ALLOWED_NON_STRICT = {"locked", "locked_with_warnings"}
ALLOWED_STRICT = {"locked"}
NON_GENERATIVE_DECISIONS = {"hold_previous", "continuation_motion"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--require-filled-prompts", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    locked_rows = load_json(Path(project["prompts"]["generation_locked_json_path"]))
    export_path = Path(project["prompts"]["fastgen_export_path"])
    generator_ready_path = Path(project["prompts"]["generator_ready_path"])
    export_report_path = Path(project["logs"]["export_report_path"])
    batches_json_path = export_path.with_suffix(".batches.json")
    batches_csv_path = export_path.with_suffix(".batches.csv")
    meta_path = export_path.with_suffix(export_path.suffix + ".meta.json")

    allowed = ALLOWED_STRICT if project["workflow"].get("strict_generation_lock") else ALLOWED_NON_STRICT
    eligible = [
        row
        for row in locked_rows
        if row["generation_lock_status"] in allowed
        and str(row.get("generation_decision") or row.get("generation_mode") or "new_image") not in NON_GENERATIVE_DECISIONS
    ]
    non_generative = [row for row in locked_rows if str(row.get("generation_decision") or row.get("generation_mode") or "") in NON_GENERATIVE_DECISIONS]
    blocked = [row["frame_id"] for row in locked_rows if row["generation_lock_status"] not in allowed]
    if args.require_filled_prompts and blocked:
        raise RuntimeError(f"Generation lock blocked frames: {', '.join(blocked[:20])}")

    text = "\n\n".join(row["generator_block"] for row in eligible).strip() + "\n"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(text, encoding="utf-8")
    if generator_ready_path != export_path:
        generator_ready_path.write_text(text, encoding="utf-8")

    package_items = [
        {
            "scene_id": row.get("scene_id"),
            "frame_id": row.get("frame_id"),
            "beat_id": row.get("beat_id"),
            "beat_priority": row.get("beat_priority", "supporting"),
            "key_beat": bool(row.get("key_beat")),
            "variant_count": int(row.get("variant_count", 1) or 1),
            "visual_slot_id": row.get("visual_slot_id", ""),
            "generation_decision": row.get("generation_decision") or row.get("generation_mode") or "new_image",
        }
        for row in eligible
    ]
    meta_payload = {
        "package_path": str(project["prompts"]["generation_locked_json_path"]),
        "package_signature": stable_hash({"eligible_frames": [row.get("frame_id") for row in eligible], "items": package_items}),
        "prompt_count": len(eligible),
        "non_generative_frame_count": len(non_generative),
        "package_items": package_items,
    }
    meta_payload["export_signature"] = stable_hash(
        {
            "package_path": meta_payload["package_path"],
            "package_signature": meta_payload["package_signature"],
            "prompt_count": meta_payload["prompt_count"],
            "content": text,
        }
    )
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    batch_rows = [
        {
            "frame_id": row["frame_id"],
            "generator_prompt": row["image_prompt"],
            "negative_prompt": row["negative_prompt"],
            "reference_images": row.get("reference_images", []),
            "reference_ids": row.get("reference_ids", []),
            "reference_strength": row.get("reference_strength", "none"),
            "reference_usage": row.get("reference_usage", "none"),
            "visual_slot_id": row.get("visual_slot_id", ""),
            "generation_decision": row.get("generation_decision") or row.get("generation_mode") or "new_image",
            "variant_count": int(row.get("variant_count", 1) or 1),
        }
        for row in eligible
    ]
    batches_json_path.write_text(json.dumps(batch_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with batches_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "frame_id",
                "generator_prompt",
                "negative_prompt",
                "reference_images",
                "reference_ids",
                "reference_strength",
                "reference_usage",
                "visual_slot_id",
                "generation_decision",
                "variant_count",
            ],
        )
        writer.writeheader()
        for row in batch_rows:
            writer.writerow(
                {
                    **row,
                    "reference_images": ";".join(row["reference_images"]),
                    "reference_ids": ",".join(row["reference_ids"]),
                }
            )

    export_report_path.write_text(
        "\n".join(
            [
                "# Export Report",
                "",
                f"Locked frames available: {len(eligible)}",
                f"Blocked frames: {len(blocked)}",
                f"Non-generative visual slots skipped: {len(non_generative)}",
                f"Strict mode: {project['workflow'].get('strict_generation_lock')}",
                f"Output: {export_path}",
                f"Batches JSON: {batches_json_path}",
                f"Batches CSV: {batches_csv_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    project["prompts"]["status"] = "generator_ready"
    project["current_stage"] = "report"
    save_project(project_json, project)
    print(export_path)


if __name__ == "__main__":
    main()
