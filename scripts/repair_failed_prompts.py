import argparse
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project
from yt_nonstop.providers.llm_provider import build_json_only_prompt, complete_json, provider_from_project


IMMUTABLE_FIELDS = [
    "beat_id",
    "visual_slot_id",
    "start",
    "end",
    "duration",
    "reference_ids",
    "film_block_id",
    "shot_type",
]

PROMPT_FIELDS = [
    "final_prompt",
    "negative_prompt",
    "visual_goal",
    "visualized_claim",
    "what_is_in_frame",
    "camera",
    "composition",
    "lighting",
    "mood",
    "continuity_notes",
    "must_not_show",
]


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("llm_prompt_drafts", "prompts", "items", "rows", "repaired_prompts"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def build_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = clean_text(row.get("frame_id") or row.get("scene_id"))
        if key:
            indexed[key] = row
    return indexed


def merge_repaired_row(original: dict[str, Any], repaired: dict[str, Any]) -> dict[str, Any]:
    merged = dict(original)
    for field in PROMPT_FIELDS:
        if field in repaired:
            merged[field] = repaired[field]
    for field in IMMUTABLE_FIELDS:
        if field in original:
            merged[field] = original[field]
    merged["repair_status"] = "repaired"
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--provider", default="", help="Prompt repair provider mode override: file, external, command, http, openai_compatible, disabled.")
    parser.add_argument("--input-json", help="Optional provider input JSON file.")
    parser.add_argument("--failed-json", help="Optional JSON file listing failed prompt rows to repair.")
    parser.add_argument("--output-json", help="Optional output path override.")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    drafts_path = Path(project["prompts"]["llm_prompt_drafts_path"])
    rows = load_rows(drafts_path)
    failed_rows = load_rows(Path(args.failed_json).resolve()) if args.failed_json else rows
    provider_config = provider_from_project(
        project,
        stage_name="repair_failed_prompts",
        override_mode=args.provider or None,
        input_json_path=str(Path(args.input_json).resolve()) if args.input_json else None,
    )
    repaired_payload = complete_json(
        "repair_failed_prompts",
        "You repair prompt wording for an image-generation pipeline. Return JSON only.",
        {
            "instruction": "Repair only prompt-facing fields while preserving immutable timing and continuity fields.",
            "immutable_fields": IMMUTABLE_FIELDS,
            "prompt_fields": PROMPT_FIELDS,
            "failed_prompts": failed_rows,
            "rules": [
                "Do not change beat_id, visual_slot_id, start, end, duration, reference_ids, film_block_id, or shot_type.",
                "Only repair prompt wording and prompt-facing fields.",
                "Do not invent file paths, statuses, or runtime claims.",
            ],
            "user_prompt": build_json_only_prompt(
                instruction="Repair the failed prompts while preserving immutable fields exactly.",
                context={"immutable_fields": IMMUTABLE_FIELDS, "failed_prompts": failed_rows},
            ),
        },
        schema_name="repair_failed_prompts.v1",
        required_keys=["repaired_prompts"],
        provider_config=provider_config,
    )
    repaired_rows = repaired_payload.get("repaired_prompts", [])
    original_by_key = build_index(rows)
    repaired_by_key = build_index([row for row in repaired_rows if isinstance(row, dict)])
    merged_rows = []
    for row in rows:
        key = clean_text(row.get("frame_id") or row.get("scene_id"))
        if key and key in repaired_by_key:
            merged_rows.append(merge_repaired_row(row, repaired_by_key[key]))
        else:
            merged_rows.append(row)

    output_path = Path(args.output_json).resolve() if args.output_json else drafts_path
    save_json(output_path, merged_rows)
    project["prompts"]["llm_prompt_drafts_path"] = str(output_path)
    project["prompts"]["repair_failed_prompts_status"] = "completed"
    project["current_stage"] = "generation_lock"
    save_project(project_json, project)
    print(output_path)


if __name__ == "__main__":
    main()
