import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json
from yt_nonstop.utils.text_repair import repair_mojibake_text, repair_payload_strings


TEXT_FIELDS = {
    "voice_text",
    "scene_summary",
    "spoken_claim",
    "visualized_claim",
    "visual_goal",
    "screen_action",
    "scene_anchor",
    "what_is_in_frame",
    "must_show",
    "notes",
}


def repair_srt_file(path: Path) -> bool:
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8-sig")
    repaired = repair_mojibake_text(original)
    if repaired == original:
        return False
    path.write_text(repaired, encoding="utf-8")
    return True


def repair_json_file(path: Path) -> tuple[bool, int]:
    if not path.exists():
        return False, 0
    payload = load_json(path)
    repaired = repair_payload_strings(payload)
    if repaired == payload:
        return False, 0
    before = str(payload)
    after = str(repaired)
    diff_count = 0 if before == after else 1
    save_json(path, repaired)
    return True, diff_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    repaired_paths: list[str] = []

    srt_paths = [
        Path(project["transcript_cleanup"]["cleaned_srt_path"]),
        Path(project["transcription"]["srt_path"]),
    ]
    for path in srt_paths:
        if path.exists() and repair_srt_file(path):
            repaired_paths.append(str(path))

    json_paths = [
        Path(project["scene_plan"]["scene_plan_path"]),
        Path(project["planning"].get("narration_beats_path", "")),
        Path(project["planning"].get("frame_briefs_json_path", "")),
        Path(project["prompts"].get("prompt_package_path", "")),
        Path(project["prompts"].get("final_scene_plan_path", "")),
    ]
    for path in json_paths:
        if path and str(path).strip():
            changed, _ = repair_json_file(path)
            if changed:
                repaired_paths.append(str(path))

    print("\n".join(repaired_paths))


if __name__ == "__main__":
    main()
