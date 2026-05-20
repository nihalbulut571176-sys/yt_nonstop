import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_text_if_present(path_str: str | None) -> str:
    if not path_str:
        return ""
    path = Path(path_str)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def extract_scene_excerpt(scene_plan_path: Path, max_items: int = 8) -> list[str]:
    if not scene_plan_path.exists():
        return []
    data = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    excerpts = []
    seen = set()
    for scene in scenes:
        text = re.sub(r"\s+", " ", str(scene.get("voice_text", "")).strip())
        if text and text not in seen:
            seen.add(text)
            excerpts.append(text)
        if len(excerpts) >= max_items:
            break
    return excerpts


def update_json_file(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    project_root = Path(project["meta"]["project_root"])
    publishing_dir = project_root / "publishing"
    publishing_dir.mkdir(parents=True, exist_ok=True)

    raw_text = load_text_if_present(project["inputs"].get("raw_text_path"))
    approved_script = load_text_if_present(project["rewrite"].get("approved_script_path"))
    rewritten_script = load_text_if_present(project["rewrite"].get("rewritten_script_path"))
    source_text = approved_script or rewritten_script or raw_text
    scene_excerpts = extract_scene_excerpt(Path(project["scene_plan"]["scene_plan_path"]))

    source_snapshot_path = publishing_dir / "source_snapshot.md"
    source_snapshot = [
        "# Publishing Source Snapshot",
        "",
        f"Project ID: {project['project_id']}",
        f"Profile: {project['profile_id']}",
        "",
        "## Preferred Source Text",
        "",
        source_text if source_text else "(No source text yet)",
        "",
        "## Transcript Excerpts",
        "",
    ]
    if scene_excerpts:
        for idx, excerpt in enumerate(scene_excerpts, start=1):
            source_snapshot.append(f"{idx}. {excerpt}")
    else:
        source_snapshot.append("(No scene excerpts yet)")
    source_snapshot.append("")
    source_snapshot_path.write_text("\n".join(source_snapshot), encoding="utf-8")

    title_drafts_path = Path(project["publishing"]["title_generation"]["drafts_path"])
    description_drafts_path = Path(project["publishing"]["description_generation"]["drafts_path"])
    thumbnail_brief_path = Path(project["publishing"]["thumbnail_generation"]["thumbnail_brief_path"])
    prompt_candidates_path = Path(project["publishing"]["thumbnail_generation"]["prompt_candidates_path"])

    title_payload = {
        "status": "ready_for_generation",
        "prompt_version": project["publishing"]["title_generation"]["prompt_version"],
        "editorial_angle": project["publishing"].get("editorial_angle"),
        "instructions": [
            "Generate 10-15 YouTube title candidates.",
            "Balance curiosity, clarity, and credibility.",
            "Avoid vague clickbait with no concrete angle.",
            "Prefer titles that reflect the actual investigation or thesis of the video.",
        ],
        "source_snapshot_path": str(source_snapshot_path),
        "drafts": [],
        "selection_notes": "",
    }
    description_payload = {
        "status": "ready_for_generation",
        "prompt_version": project["publishing"]["description_generation"]["prompt_version"],
        "editorial_angle": project["publishing"].get("editorial_angle"),
        "instructions": [
            "Generate 2-3 YouTube description variants.",
            "Lead with a strong opening paragraph.",
            "Preserve factual alignment with the script.",
            "Leave room for links, credits, and CTA if needed.",
        ],
        "source_snapshot_path": str(source_snapshot_path),
        "drafts": [],
        "selection_notes": "",
    }
    thumbnail_payload = {
        "status": "ready_for_generation",
        "prompt_version": project["publishing"]["thumbnail_generation"]["prompt_version"],
        "editorial_angle": project["publishing"].get("editorial_angle"),
        "instructions": [
            "Create 5-10 thumbnail prompt candidates for FastGen.",
            "Prioritize one strong visual conflict.",
            "Optimize for YouTube thumbnail readability and emotional clarity.",
            "Avoid overloading the image with too many concepts.",
        ],
        "source_snapshot_path": str(source_snapshot_path),
        "candidates": [],
        "selection_notes": "",
    }
    update_json_file(title_drafts_path, title_payload)
    update_json_file(description_drafts_path, description_payload)
    update_json_file(prompt_candidates_path, thumbnail_payload)

    brief_lines = [
        "# Thumbnail Brief",
        "",
        f"Project ID: {project['project_id']}",
        f"Profile: {project['profile_id']}",
        "",
        "Working angle:",
        project["publishing"].get("editorial_angle") or "",
        "",
        "Core promise of the video:",
        "",
        "Main conflict or reveal:",
        "",
        "Best candidate visual subjects:",
    ]
    if scene_excerpts:
        for excerpt in scene_excerpts[:5]:
            brief_lines.append(f"- {excerpt}")
    else:
        brief_lines.append("- Add after scene plan is reviewed")
    brief_lines.extend(
        [
            "",
            "Possible text on thumbnail:",
            "",
            "Things to avoid:",
            "- Too many objects in one frame",
            "- Weak emotional signal",
            "- Generic stock-looking composition",
            "",
        ]
    )
    thumbnail_brief_path.write_text("\n".join(brief_lines), encoding="utf-8")

    project["publishing"]["status"] = "ready_for_generation"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(source_snapshot_path)
    print(title_drafts_path)
    print(description_drafts_path)
    print(thumbnail_brief_path)
    print(prompt_candidates_path)


if __name__ == "__main__":
    main()
