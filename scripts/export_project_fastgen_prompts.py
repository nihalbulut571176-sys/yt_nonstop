import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_reference_prefix(reference_ids: list[str]) -> str:
    if not reference_ids:
        return "No character reference."
    if len(reference_ids) == 1:
        return f"Use reference image: {reference_ids[0]}."
    return f"Use reference images: {', '.join(reference_ids)}."


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

    blocks = []
    missing = []
    for item in package.get("items", []):
        prompt = str(item.get("prompt", "")).strip()
        if not prompt:
            missing.append(item["scene_id"])
            if args.require_filled_prompts:
                continue
        prefix = build_reference_prefix(item.get("reference_ids", []))
        blocks.append(f"{prefix} {prompt}".strip())

    if args.require_filled_prompts and missing:
        raise RuntimeError(f"Missing prompts for scenes: {', '.join(missing[:20])}")

    generator_ready_path.write_text("\n\n".join(blocks).strip() + "\n", encoding="utf-8")
    project["prompts"]["status"] = "generator_ready"
    project["current_stage"] = "images"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(generator_ready_path)


if __name__ == "__main__":
    main()
