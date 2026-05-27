import argparse
import json
import re
from pathlib import Path

from project_pipeline_utils import load_project, save_project
from prompt_safety import build_prompt_guardrail


VIDEO_MOTION_SUFFIX = (
    "Natural documentary video, realistic motion and temporal continuity. "
    "Use subtle body movement, breathing, blinking, head turns, slow walking, shifting weight, moving fur, wind, snow, mist, water, or grass when appropriate. "
    "Keep the camera grounded and cinematic: slow handheld drift, tripod lockoff, or gentle tracking only. "
    "No surreal morphing, no sudden transformations, no extra limbs, no text, no watermark, no logo. "
    "No voiceover, no spoken narration, no dialogue, no lip-sync, no singing, no on-screen captions, no subtitles. "
    "If any audio is present, it should be only subtle natural ambience appropriate to the environment."
)


def adapt_prompt_for_video(prompt: str) -> str:
    text = re.sub(r"\s+", " ", prompt).strip()
    replacements = [
        (r"\bdocumentary still\b", "cinematic documentary video"),
        (r"\bultra-realistic cinematic documentary still\b", "ultra-realistic cinematic documentary video"),
        (r"\bbase the image on this narration fragment\b", "Base the video on this narration fragment"),
        (r"\bbase the image on\b", "Base the video on"),
        (r"\bshow\b", "Show"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    if re.search(r"\bstill image\b|\bstill\b|\bphoto(graph)?\b", text, flags=re.IGNORECASE):
        text = re.sub(r"\bstill image\b", "video scene", text, flags=re.IGNORECASE)
        text = re.sub(r"\bdocumentary still\b", "documentary video", text, flags=re.IGNORECASE)
        text = re.sub(r"\bstill\b", "video", text, flags=re.IGNORECASE)
        text = re.sub(r"\bphotograph\b|\bphoto\b", "video shot", text, flags=re.IGNORECASE)

    if VIDEO_MOTION_SUFFIX.lower() not in text.lower():
        text = f"{text} {VIDEO_MOTION_SUFFIX}".strip()
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--require-filled-prompts", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
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
        guardrail = build_prompt_guardrail(item)
        if guardrail and guardrail not in prompt:
            prompt = f"{prompt} {guardrail}".strip()
        blocks.append(adapt_prompt_for_video(prompt))

    if args.require_filled_prompts and missing:
        raise RuntimeError(f"Missing prompts for scenes: {', '.join(missing[:20])}")

    generator_ready_path.write_text("\n\n".join(blocks).strip() + "\n", encoding="utf-8")
    project["prompts"]["status"] = "generator_ready"
    project["current_stage"] = "generate_videos"
    save_project(project_json, project)

    print(generator_ready_path)


if __name__ == "__main__":
    main()
