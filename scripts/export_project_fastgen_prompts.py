import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from prompt_continuity import stable_hash


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_reference_prefix(reference_ids: list[str]) -> str:
    if not reference_ids:
        return "No character reference."
    if len(reference_ids) == 1:
        return f"Use reference image: {reference_ids[0]}."
    return f"Use reference images: {', '.join(reference_ids)}."


def flatten_prompt(prompt: str) -> str:
    return " ".join(str(prompt or "").split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--require-filled-prompts", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    package = json.loads(prompt_package_path.read_text(encoding="utf-8"))
    generator_ready_path = Path(project["prompts"]["generator_ready_path"])
    export_meta_path = generator_ready_path.with_suffix(generator_ready_path.suffix + ".meta.json")

    qa_status = package.get("qa_status", {}).get("status")
    if qa_status != "passed":
        raise RuntimeError(f"Prompt package QA status is {qa_status!r}; refusing export")

    blocks = []
    missing = []
    for item in package.get("items", []):
        prompt = flatten_prompt(item.get("prompt", ""))
        if not prompt:
            missing.append(item["scene_id"])
            if args.require_filled_prompts:
                continue
        prefix = build_reference_prefix(item.get("reference_ids", []))
        blocks.append(f"{prefix} {prompt}".strip())

    if args.require_filled_prompts and missing:
        raise RuntimeError(f"Missing prompts for scenes: {', '.join(missing[:20])}")

    if len(blocks) != package.get("scene_count"):
        raise RuntimeError("Prompt block count does not match package scene_count")

    export_text = "\n\n".join(blocks).strip() + "\n"
    export_signature = stable_hash(
        {
            "package_path": str(prompt_package_path),
            "package_signature": package.get("source_signature"),
            "prompt_count": len(blocks),
            "content": export_text,
        }
    )
    generator_ready_path.write_text(export_text, encoding="utf-8")
    export_meta = {
        "generated_at": iso_now(),
        "project_id": project["project_id"],
        "package_path": str(prompt_package_path),
        "package_signature": package.get("source_signature"),
        "package_scene_count": package.get("scene_count"),
        "prompt_count": len(blocks),
        "export_signature": export_signature,
        "generator_ready_path": str(generator_ready_path),
        "profile_id": project.get("profile_id"),
        "package_items": [
            {
                "scene_id": item.get("scene_id"),
                "beat_priority": item.get("beat_priority", "standard"),
                "key_beat": bool(item.get("key_beat")),
                "variant_count": int(item.get("variant_count", 1) or 1),
                "reference_ids": item.get("reference_ids", []),
            }
            for item in package.get("items", [])
        ],
    }
    export_meta_path.write_text(json.dumps(export_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    project["prompts"]["status"] = "generator_ready"
    project["prompts"]["export_meta_path"] = str(export_meta_path)
    project["current_stage"] = "images"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(generator_ready_path)
    print(export_meta_path)


if __name__ == "__main__":
    main()
