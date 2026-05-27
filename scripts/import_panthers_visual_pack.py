import argparse
import csv
import json
import re
import shutil
from pathlib import Path

from project_pipeline_utils import load_project, save_json, save_project


SECTION_PATTERN = re.compile(
    r"(?ms)^([A-Za-z][A-Za-z ]+):\n(.*?)(?=^[A-Za-z][A-Za-z ]+:\n|\Z)"
)


def parse_timecode(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def extract_prompt_sections(prompt: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for key, body in SECTION_PATTERN.findall(prompt.strip()):
        normalized = key.strip().lower().replace(" ", "_")
        sections[normalized] = body.strip()
    return sections


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_long_segment_report(scenes: list[dict], max_duration: float) -> dict:
    over_limit = []
    for scene in scenes:
        duration = float(scene["duration"])
        if duration > max_duration:
            over_limit.append(
                {
                    "scene_id": scene["scene_id"],
                    "duration": duration,
                    "over_by_seconds": round(duration - max_duration, 3),
                }
            )
    return {
        "max_still_duration_seconds": max_duration,
        "scene_count": len(scenes),
        "over_limit_count": len(over_limit),
        "over_limit_scenes": over_limit,
    }


def build_style_guide(pack_scene_plan: dict, pack_visual_bible_md: str) -> dict:
    project_meta = pack_scene_plan.get("project", {})
    bible_meta = pack_scene_plan.get("visual_bible", {})
    style_summary = " | ".join(
        filter(
            None,
            [
                str(project_meta.get("visual_style", "")).strip(),
                str(bible_meta.get("main_mood", "")).strip(),
                str(bible_meta.get("camera_language", "")).strip(),
            ],
        )
    )
    return {
        "style_summary": style_summary,
        "aspect_ratio": project_meta.get("aspect_ratio", "16:9"),
        "main_mood": bible_meta.get("main_mood", ""),
        "camera_language": bible_meta.get("camera_language", ""),
        "color_palette": bible_meta.get("color_palette", ""),
        "recurring_motifs": bible_meta.get("recurring_motifs", []),
        "forbidden_visuals": bible_meta.get("forbidden_visuals", []),
        "source_visual_bible_markdown": pack_visual_bible_md,
    }


def build_scene_and_prompt_records(
    image_rows: list[dict[str, str]],
    variant_rows: list[dict[str, str]],
) -> tuple[list[dict], list[dict], list[str]]:
    variants_by_beat: dict[str, list[dict[str, str]]] = {}
    for row in variant_rows:
        variants_by_beat.setdefault(row["beat_id"], []).append(row)

    scenes: list[dict] = []
    prompt_items: list[dict] = []
    review_blocks: list[str] = []

    for shot_index, row in enumerate(image_rows, start=1):
        sections = extract_prompt_sections(row["image_prompt_en"])
        scene_id = row["beat_id"]
        start_seconds = parse_timecode(row["start_time"])
        end_seconds = parse_timecode(row["end_time"])
        duration = float(row["duration_sec"])
        quality_target = float(row.get("quality_score_target") or 8.5)
        has_variants = scene_id in variants_by_beat
        scene_importance = "hero" if has_variants or quality_target >= 9 else "standard"

        visual_goal = sections.get("scene_meaning") or sections.get("visual") or row.get("visual_strategy", "")
        what_is_in_frame = sections.get("visual", "")
        scene = {
            "scene_id": scene_id,
            "shot_index": shot_index,
            "source_segment_id": int(row["srt_id"]),
            "source_index": int(row["srt_id"]),
            "part_index": 1,
            "parts_total": 1,
            "start": round(start_seconds, 3),
            "end": round(end_seconds, 3),
            "duration": duration,
            "voice_text": row["voiceover_excerpt_ru"],
            "visual_goal": visual_goal,
            "prompt": row["image_prompt_en"],
            "reference_ids": [],
            "reference_mode": "none",
            "source_kind": "imported_panthers_visual_pack",
            "generated_index": None,
            "still_image_path": None,
            "should_animate": False,
            "animation_policy_reason": "fastgen_only_no_animation",
            "animation_status": "skipped",
            "video_path": None,
            "render_source": "missing",
            "render_asset_path": None,
            "notes": [
                "Imported from panthers_visual_pack",
                "Prompt imported from pre-authored visual pack",
            ],
            "scene_importance": scene_importance,
            "shot_id": f"shot_{scene_id.lower()}",
            "source_shot_id": f"shot_{scene_id.lower()}",
            "generation_mode": "unique",
            "variation_note": "A/B/C variants available" if has_variants else "",
            "shot_role": row.get("visual_function", ""),
            "primary_subject": what_is_in_frame,
            "what_is_in_frame": what_is_in_frame,
            "camera": sections.get("camera", ""),
            "composition": sections.get("composition", row.get("shot_type", "")),
            "lighting": sections.get("lighting", ""),
            "mood": sections.get("mood", row.get("visual_function", "")),
            "negative_prompt": row.get("negative_prompt", ""),
        }
        scenes.append(scene)

        prompt_item = {
            "scene_id": scene["scene_id"],
            "shot_index": scene["shot_index"],
            "source_segment_id": scene["source_segment_id"],
            "part_index": scene["part_index"],
            "parts_total": scene["parts_total"],
            "start": scene["start"],
            "end": scene["end"],
            "duration": scene["duration"],
            "voice_text": scene["voice_text"],
            "visual_goal": scene["visual_goal"],
            "scene_importance": scene["scene_importance"],
            "shot_id": scene["shot_id"],
            "source_shot_id": scene["source_shot_id"],
            "generation_mode": scene["generation_mode"],
            "variation_note": scene["variation_note"],
            "primary_subject": scene["primary_subject"],
            "what_is_in_frame": scene["what_is_in_frame"],
            "camera": scene["camera"],
            "composition": scene["composition"],
            "lighting": scene["lighting"],
            "mood": scene["mood"],
            "negative_prompt": scene["negative_prompt"],
            "reference_ids": [],
            "reference_mode": "none",
            "prompt": scene["prompt"],
            "status": "imported_prompt",
            "notes": ["Imported from panthers_visual_pack"],
        }
        prompt_items.append(prompt_item)

        review_blocks.append(
            "\n".join(
                [
                    f"Scene {shot_index} ({scene_id})",
                    f"Timing: {scene['start']:.3f}-{scene['end']:.3f}s",
                    f"Duration: {scene['duration']:.3f}s",
                    f"Voice text: {scene['voice_text']}",
                    f"Visual function: {row.get('visual_function', '')}",
                    f"Visual strategy: {row.get('visual_strategy', '')}",
                    f"Scene importance: {scene_importance}",
                    "Visual goal:",
                    scene["visual_goal"],
                    "Prompt:",
                    scene["prompt"],
                ]
            ).rstrip()
        )

    return scenes, prompt_items, review_blocks


def copy_pack_files(pack_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in pack_dir.iterdir():
        destination = target_dir / child.name
        if child.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def write_generation_runbook(project_root: Path, project_json: Path) -> None:
    runbook = project_root / "README_generation_ready.md"
    runbook.write_text(
        "\n".join(
            [
                "# Generation Ready",
                "",
                "This project was prepared from `panthers_visual_pack` and is ready for FastGen image generation.",
                "",
                "## Start commands",
                "",
                "Generate images only:",
                f"`python scripts/run_project_fastgen_generation.py --project-json \"{project_json}\" --size 1024x1024 --concurrency 10 --retry-rounds 3 --soften-policy-prompts`",
                "",
                "Or export prompts again before generation:",
                f"`python scripts/export_project_fastgen_prompts.py --project-json \"{project_json}\" --require-filled-prompts`",
                "",
                "## Imported sources",
                "",
                "- `imported_visual_pack/scene_plan.json`",
                "- `imported_visual_pack/image_prompts.csv`",
                "- `imported_visual_pack/keyframe_variants.csv`",
                "- `imported_visual_pack/motion_plan.csv`",
                "- `imported_visual_pack/visual_bible.md`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--pack-dir", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    pack_dir = Path(args.pack_dir).resolve()
    project = load_project(project_json)
    project_root = Path(project["meta"]["project_root"])

    imported_pack_dir = project_root / "imported_visual_pack"
    copy_pack_files(pack_dir, imported_pack_dir)

    pack_scene_plan = json.loads((pack_dir / "scene_plan.json").read_text(encoding="utf-8-sig"))
    visual_bible_md = (pack_dir / "visual_bible.md").read_text(encoding="utf-8-sig")
    image_rows = load_csv_rows(pack_dir / "image_prompts.csv")
    variant_rows = load_csv_rows(pack_dir / "keyframe_variants.csv")

    scenes, prompt_items, review_blocks = build_scene_and_prompt_records(image_rows, variant_rows)

    max_duration = max(float(project["scene_plan"].get("max_still_duration_seconds") or 0), 8.0)
    project["scene_plan"]["max_still_duration_seconds"] = max_duration
    project["scene_plan"]["scene_count"] = len(scenes)
    project["scene_plan"]["original_segment_count"] = len(scenes)
    project["scene_plan"]["status"] = "completed"

    project["prompts"]["reference_mapping_path"] = str(project_root / "prompts" / "fastgen_ref_paths.json")
    project["prompts"]["visual_bible_path"] = str(project_root / "prompts" / "visual_bible.json")
    project["prompts"]["visual_bible_review_path"] = str(project_root / "prompts" / "visual_bible_review.md")
    project["prompts"]["global_style_summary"] = pack_scene_plan.get("project", {}).get("visual_style")
    project["prompts"]["status"] = "generator_ready"
    project["current_stage"] = "images"
    project["notes"].append("Imported pre-authored panthers visual pack for direct FastGen generation")

    scene_plan_payload = {
        "project": pack_scene_plan.get("project", {}),
        "visual_bible": pack_scene_plan.get("visual_bible", {}),
        "section_summary": pack_scene_plan.get("section_summary", []),
        "scenes": scenes,
    }
    prompt_package_payload = {
        "project_id": project["project_id"],
        "profile_id": project["profile_id"],
        "schema_version": project["schema_version"],
        "source_language": project["meta"].get("language", "ru"),
        "prompt_language": project["prompts"]["prompt_language"],
        "style_preset": project["prompts"]["style_preset"],
        "global_style_summary": project["prompts"].get("global_style_summary"),
        "scene_count": len(prompt_items),
        "items": prompt_items,
    }
    style_guide_payload = build_style_guide(pack_scene_plan, visual_bible_md)
    long_segment_report = build_long_segment_report(scenes, max_duration)

    save_json(Path(project["scene_plan"]["scene_plan_path"]), scene_plan_payload)
    save_json(Path(project["scene_plan"]["long_segment_report_path"]), long_segment_report)
    save_json(Path(project["prompts"]["prompt_package_path"]), prompt_package_payload)
    save_json(Path(project["prompts"]["style_guide_path"]), style_guide_payload)
    save_json(Path(project["prompts"]["visual_bible_path"]), pack_scene_plan.get("visual_bible", {}))
    save_json(Path(project["prompts"]["reference_mapping_path"]), {})

    Path(project["prompts"]["prompt_review_path"]).write_text("\n\n".join(review_blocks) + "\n", encoding="utf-8")
    Path(project["prompts"]["generator_ready_path"]).write_text(
        "\n\n".join(f"No character reference. {item['prompt']}".strip() for item in prompt_items) + "\n",
        encoding="utf-8",
    )
    Path(project["prompts"]["visual_bible_review_path"]).write_text(visual_bible_md, encoding="utf-8")

    write_generation_runbook(project_root, project_json)
    save_project(project_json, project)

    print(project["scene_plan"]["scene_plan_path"])
    print(project["prompts"]["prompt_package_path"])
    print(project["prompts"]["generator_ready_path"])


if __name__ == "__main__":
    main()
