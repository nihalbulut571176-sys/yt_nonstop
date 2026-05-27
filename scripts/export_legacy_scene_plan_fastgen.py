import argparse
import json
import re
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_reference_prefix(reference_ids: list[str]) -> str:
    if not reference_ids:
        return "No character reference."
    if len(reference_ids) == 1:
        return f"Use reference image: {reference_ids[0]}."
    return f"Use reference images: {', '.join(reference_ids)}."


def normalize_reference_ids(item: dict) -> list[str]:
    refs = item.get("reference_ids")
    if isinstance(refs, list):
        return [str(ref).strip() for ref in refs if str(ref).strip()]
    return []


def adapt_prompt_for_fastgen_still(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""

    text = re.sub(
        r"Single\s+\d+-second video shot for a [\d.]+-second timeline segment\.\s*",
        "Single cinematic still frame for a documentary montage. ",
        text,
        count=1,
    )
    text = text.replace("Keep the shot silent and usable under separate Russian voice-over;", "Keep the frame silent and usable under separate Russian voice-over;")
    text = text.replace("Visual goal:", "Still-frame goal:")
    text = text.replace("Shot variation:", "Frame variation:")
    text = text.replace("16:9 composition.", "16:9 composition, optimized for a single high-detail still image.")
    return text


def build_prompt_package(scene_plan: dict) -> dict:
    items = []
    for shot_index, item in enumerate(scene_plan.get("items", []), start=1):
        refs = normalize_reference_ids(item)
        source_srt_indices = item.get("source_srt_indices", [])
        source_segment_id = source_srt_indices[0] if source_srt_indices else shot_index
        package_item = {
            "scene_id": item["scene_id"],
            "shot_index": shot_index,
            "source_segment_id": source_segment_id,
            "part_index": 1,
            "parts_total": 1,
            "start": item["start"],
            "end": item["end"],
            "duration": item["duration"],
            "voice_text": item.get("voice_text", ""),
            "visual_goal": item.get("visual_goal", ""),
            "scene_importance": item.get("scene_importance", ""),
            "shot_id": item.get("scene_id", ""),
            "source_shot_id": item.get("scene_id", ""),
            "generation_mode": "unique",
            "variation_note": item.get("shot_variation", ""),
            "primary_subject": item.get("shot_role", ""),
            "what_is_in_frame": item.get("visual_goal", ""),
            "camera": item.get("shot_variation", ""),
            "composition": "keep the frame documentary-like and physically grounded",
            "lighting": item.get("lighting", ""),
            "mood": item.get("mood", ""),
            "negative_prompt": item.get("negative_prompt", scene_plan.get("global_negative_prompt", "")),
            "reference_ids": refs,
            "reference_mode": "multiple" if len(refs) > 1 else ("single" if refs else "none"),
            "prompt": adapt_prompt_for_fastgen_still(item.get("prompt", "")),
            "status": "pending_prompt",
            "notes": [],
            "legacy_source_srt_indices": source_srt_indices,
            "legacy_timecodes": {
                "start_timecode": item.get("start_timecode"),
                "end_timecode": item.get("end_timecode"),
            },
        }
        items.append(package_item)

    return {
        "project_id": scene_plan.get("project_id", "legacy_scene_plan"),
        "profile_id": "fastgen_only",
        "schema_version": scene_plan.get("schema_version", "legacy-items-export"),
        "source_language": scene_plan.get("source_language", "ru"),
        "prompt_language": scene_plan.get("prompt_language", "English"),
        "style_preset": "legacy-scene-plan-export",
        "global_style_summary": scene_plan.get("global_style", ""),
        "scene_count": len(items),
        "items": items,
    }


def build_generator_ready(package: dict) -> str:
    blocks = []
    for item in package.get("items", []):
        prefix = build_reference_prefix(item.get("reference_ids", []))
        prompt = str(item.get("prompt", "")).strip()
        if not prompt:
            continue
        blocks.append(f"{prefix} {prompt}".strip())
    return "\n\n".join(blocks).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--out-package", required=True)
    parser.add_argument("--out-generator-ready", required=True)
    args = parser.parse_args()

    scene_plan_path = Path(args.scene_plan).resolve()
    out_package_path = Path(args.out_package).resolve()
    out_generator_ready_path = Path(args.out_generator_ready).resolve()

    scene_plan = load_json(scene_plan_path)
    if "items" not in scene_plan:
        raise RuntimeError(f"Legacy scene plan with 'items' array expected: {scene_plan_path}")

    package = build_prompt_package(scene_plan)
    generator_ready = build_generator_ready(package)

    out_package_path.parent.mkdir(parents=True, exist_ok=True)
    out_generator_ready_path.parent.mkdir(parents=True, exist_ok=True)

    out_package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    out_generator_ready_path.write_text(generator_ready, encoding="utf-8")

    print(out_package_path)
    print(out_generator_ready_path)


if __name__ == "__main__":
    main()
