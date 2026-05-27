import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project
from prompt_safety import build_prompt_guardrail


def normalize_prompt_block(prompt: str) -> str:
    return " ".join(str(prompt).split())


def build_reference_prefix(reference_ids: list[str]) -> str:
    if not reference_ids:
        return "No character reference."
    if len(reference_ids) == 1:
        return f"Use reference image: {reference_ids[0]}."
    return f"Use reference images: {', '.join(reference_ids)}."


def choose_export_prompt(scene: dict) -> str:
    prompt = str(scene.get("prompt", "")).strip()
    final_prompt = str(scene.get("final_prompt", "")).strip()
    structured_markers = (
        "Create a premium cinematic documentary still",
        "Scene meaning:",
        "Visual strategy:",
        "Restrictions:",
    )
    if prompt and any(marker in prompt for marker in structured_markers):
        return prompt
    return final_prompt or prompt


def block_for_scene(scene: dict) -> str:
    prompt = normalize_prompt_block(choose_export_prompt(scene))
    guardrail = build_prompt_guardrail(scene)
    if guardrail and guardrail not in prompt:
        prompt = normalize_prompt_block(f"{prompt} {guardrail}")
    prefix = build_reference_prefix(scene.get("reference_ids", []))
    return f"{prefix} {prompt}".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--require-filled-prompts", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    fastgen_export_path = Path(project["prompts"]["fastgen_export_path"])
    generator_ready_path = Path(project["prompts"]["generator_ready_path"])
    export_report_path = Path(project["logs"]["export_report_path"])

    source_path = final_scene_plan_path if final_scene_plan_path.exists() else Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(source_path.read_text(encoding="utf-8"))
    prompt_package = json.loads(prompt_package_path.read_text(encoding="utf-8"))

    blocks = []
    missing = []
    for scene in scene_plan.get("scenes", []):
        prompt = normalize_prompt_block(choose_export_prompt(scene))
        if not prompt:
            missing.append(scene["scene_id"])
            if args.require_filled_prompts:
                continue
        blocks.append(block_for_scene(scene))

    if args.require_filled_prompts and missing:
        raise RuntimeError(f"Missing prompts for scenes: {', '.join(missing[:20])}")

    fastgen_export_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n\n".join(blocks).strip() + "\n"
    fastgen_export_path.write_text(text, encoding="utf-8")
    if generator_ready_path != fastgen_export_path:
        generator_ready_path.parent.mkdir(parents=True, exist_ok=True)
        generator_ready_path.write_text(text, encoding="utf-8")

    prompt_package["export_path"] = str(fastgen_export_path)
    for item in prompt_package.get("items", []):
        if not item.get("final_prompt") and item.get("prompt"):
            item["final_prompt"] = item["prompt"]
    prompt_package_path.write_text(json.dumps(prompt_package, ensure_ascii=False, indent=2), encoding="utf-8")

    export_report_lines = [
        "# Export Report",
        "",
        f"Source scene plan: {source_path}",
        f"Prompt package: {prompt_package_path}",
        f"Exported blocks: {len(blocks)}",
        f"Missing final prompts: {len(missing)}",
        f"Output: {fastgen_export_path}",
    ]
    if missing:
        export_report_lines.extend(["", "Missing scene IDs:", *[f"- {scene_id}" for scene_id in missing[:50]]])
    export_report_path.write_text("\n".join(export_report_lines) + "\n", encoding="utf-8")

    project["prompts"]["status"] = "generator_ready"
    project["current_stage"] = "final_review"
    save_project(project_json, project)

    print(fastgen_export_path)


if __name__ == "__main__":
    main()
