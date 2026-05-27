import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from prompt_continuity import build_beat_report, extract_scene_semantics, infer_theme, read_source_text


SENTENCE_END_RE = re.compile(r"[.!?…]$|[.!?…][\"'»”)]$")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_srt_timestamp(tc: str) -> float:
    hh, mm, rest = tc.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def parse_srt(text: str) -> list[dict]:
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        start_tc, end_tc = lines[1].split(" --> ")
        content = " ".join(line.strip() for line in lines[2:])
        segments.append(
            {
                "start_tc": start_tc,
                "end_tc": end_tc,
                "start": parse_srt_timestamp(start_tc),
                "end": parse_srt_timestamp(end_tc),
                "text": re.sub(r"\s+", " ", content).strip(),
            }
        )
    return segments


def merge_into_sentence_blocks(segments: list[dict]) -> list[dict]:
    sentence_blocks = []
    current = []
    for seg in segments:
        current.append(seg)
        if SENTENCE_END_RE.search(seg["text"]):
            sentence_blocks.append(
                {
                    "segment_id": len(sentence_blocks) + 1,
                    "start": current[0]["start"],
                    "end": current[-1]["end"],
                    "start_tc": current[0]["start_tc"],
                    "end_tc": current[-1]["end_tc"],
                    "text": re.sub(r"\s+", " ", " ".join(item["text"] for item in current)).strip(),
                }
            )
            current = []
    if current:
        sentence_blocks.append(
            {
                "segment_id": len(sentence_blocks) + 1,
                "start": current[0]["start"],
                "end": current[-1]["end"],
                "start_tc": current[0]["start_tc"],
                "end_tc": current[-1]["end_tc"],
                "text": re.sub(r"\s+", " ", " ".join(item["text"] for item in current)).strip(),
            }
        )
    return sentence_blocks


def split_duration(total: float, parts: int) -> list[float]:
    base = total / parts
    durations = [round(base, 6) for _ in range(parts)]
    correction = round(total - sum(durations), 6)
    durations[-1] = round(durations[-1] + correction, 6)
    return durations


def choose_alternate(value: str, options: list[str]) -> str:
    for option in options:
        if option != value:
            return option
    return value


def apply_retention_direction(scenes: list[dict]) -> None:
    scale_cycle = ["wide", "medium", "close-up", "macro"]
    angle_cycle = ["eye-level", "low angle", "high angle", "over-the-shoulder", "top-down"]
    density_cycle = ["clean", "layered", "focused", "busy"]

    for index, scene in enumerate(scenes):
        scene["opening_window"] = scene["start"] < 60.0
        if scene["opening_window"] and scene["shot_index"] <= 3 and scene["visual_function"] == "transition":
            scene["visual_function"] = "hook"
            scene["beat_priority"] = "hero"
            scene["key_beat"] = True
            scene["viewer_emotion"] = "mystery"
            scene["notes"].append("Opening-minute escalation promoted this beat to a hook.")

        if index == 0:
            scene["pattern_break_score"] = 8.5 if scene["key_beat"] else 7.0
            scene["diversity_axes_from_previous"] = []
            continue

        previous = scenes[index - 1]
        diversity_axes = []
        if previous["scale"] != scene["scale"]:
            diversity_axes.append("scale")
        if previous["angle"] != scene["angle"]:
            diversity_axes.append("angle")
        if previous["lighting_family"] != scene["lighting_family"]:
            diversity_axes.append("lighting_family")
        if previous["density"] != scene["density"]:
            diversity_axes.append("density")
        if previous["visual_function"] != scene["visual_function"]:
            diversity_axes.append("visual_function")
        if previous["environment"] != scene["environment"]:
            diversity_axes.append("environment")

        if len(diversity_axes) < 2:
            original_scale = scene["scale"]
            original_angle = scene["angle"]
            original_density = scene["density"]
            scene["scale"] = choose_alternate(original_scale, scale_cycle)
            scene["angle"] = choose_alternate(original_angle, angle_cycle)
            scene["density"] = choose_alternate(original_density, density_cycle)
            diversity_axes = ["scale", "angle", "density"]
            scene["notes"].append("Adjacent-shot diversity boost applied to avoid slideshow repetition.")

        if (
            index >= 2
            and scene["visual_strategy"] == previous["visual_strategy"] == scenes[index - 2]["visual_strategy"] == "mechanism_view"
        ):
            scene["pattern_break_score"] = 9.0
            scene["visual_function"] = "pattern_break"
            scene["density"] = choose_alternate(scene["density"], density_cycle)
            scene["notes"].append("Analytical streak detected; this beat was turned into a pattern-break frame.")
        else:
            scene["pattern_break_score"] = 8.5 if scene["key_beat"] else max(6.0, 5.5 + len(diversity_axes))

        scene["diversity_axes_from_previous"] = diversity_axes


def build_scene_plan(
    sentence_blocks: list[dict], max_duration: float, theme_hint: str
) -> tuple[list[dict], list[dict]]:
    scenes = []
    long_segments = []

    for block in sentence_blocks:
        duration = round(block["end"] - block["start"], 6)
        parts = max(1, int(math.ceil(duration / max_duration)))
        part_durations = split_duration(duration, parts)

        if parts > 1:
            long_segments.append(
                {
                    "source_segment_id": block["segment_id"],
                    "start": block["start"],
                    "end": block["end"],
                    "duration": duration,
                    "parts": parts,
                    "text": block["text"],
                }
            )

        cursor = block["start"]
        for idx, part_duration in enumerate(part_durations, start=1):
            part_start = round(cursor, 6)
            part_end = round(cursor + part_duration, 6)
            cursor = part_end

            scene = {
                "scene_id": f"scene_{len(scenes) + 1:04d}",
                "shot_index": len(scenes) + 1,
                "source_segment_id": block["segment_id"],
                "source_index": block["segment_id"],
                "part_index": idx,
                "parts_total": parts,
                "start": part_start,
                "end": part_end,
                "duration": round(part_duration, 6),
                "voice_text": block["text"],
                "visual_goal": "",
                "prompt": "",
                "shot_role": "",
                "viewer_emotion": "",
                "scale": "medium",
                "primary_subject": "",
                "environment": "",
                "composition": "",
                "angle": "",
                "lighting": "",
                "lighting_family": "neutral",
                "atmosphere": "",
                "density": "layered",
                "pattern_break_score": 0.0,
                "diversity_axes_from_previous": [],
                "beat_priority": "standard",
                "key_beat": False,
                "active_entity_ids": [],
                "continuity_cast": [],
                "continuity_focus": "",
                "reference_ids": [],
                "reference_mode": "none",
                "source_kind": "original" if idx == 1 else "extra",
                "generated_index": None,
                "still_image_path": None,
                "should_animate": False,
                "animation_policy_reason": "fastgen_only_no_animation",
                "animation_status": "skipped",
                "video_path": None,
                "render_source": "missing",
                "render_asset_path": None,
                "notes": [
                    "Prompt pending",
                    "Still image pending",
                ],
            }
            scene.update(extract_scene_semantics(scene, theme_hint))
            scenes.append(scene)

    apply_retention_direction(scenes)
    return scenes, long_segments


def write_sentence_block_text(path: Path, blocks: list[dict]) -> None:
    lines = []
    for item in blocks:
        lines.append(f"{item['segment_id']}. [{item['start_tc']} - {item['end_tc']}] {item['text']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_scene_prompt_seed(path: Path, scenes: list[dict]) -> None:
    blocks = []
    for scene in scenes:
        block = [
            f"Scene {scene['shot_index']} ({scene['start']:.3f}-{scene['end']:.3f}s)",
            f"Voice text: {scene['voice_text']}",
            "Visual goal:",
            "Prompt:",
            "References:",
        ]
        blocks.append("\n".join(block))
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    srt_path = Path(project["scene_plan"].get("source_srt_path") or project["transcription"]["srt_path"])
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT not found: {srt_path}")

    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan_dir = scene_plan_path.parent
    scene_plan_dir.mkdir(parents=True, exist_ok=True)

    max_duration = float(project["scene_plan"]["max_still_duration_seconds"])
    segments = parse_srt(srt_path.read_text(encoding="utf-8"))
    sentence_blocks = merge_into_sentence_blocks(segments)
    source_text = read_source_text(project)
    theme_hint = infer_theme(project, source_text, [{"voice_text": item["text"]} for item in sentence_blocks])
    scenes, long_segments = build_scene_plan(sentence_blocks, max_duration, theme_hint)

    sentence_blocks_json_path = scene_plan_dir / "sentence_blocks.json"
    sentence_blocks_txt_path = scene_plan_dir / "sentence_blocks.txt"
    long_segment_report_path = Path(project["scene_plan"]["long_segment_report_path"])
    scene_prompts_seed_path = Path(project["prompts"]["prompt_export_path"])
    logs_dir = Path(project["meta"]["project_root"]) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    beat_report_path = logs_dir / "beat_extraction_report.md"
    script_analysis_report_path = logs_dir / "script_analysis_report.md"

    sentence_blocks_json_path.write_text(json.dumps(sentence_blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    write_sentence_block_text(sentence_blocks_txt_path, sentence_blocks)
    long_segment_report_path.write_text(
        json.dumps(
            {
                "max_duration_seconds": max_duration,
                "original_segments": len(sentence_blocks),
                "long_segments": len(long_segments),
                "final_scene_count": len(scenes),
                "segments": long_segments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    scene_plan = {
        "project_id": project["project_id"],
        "schema_version": project["schema_version"],
        "source_srt_path": str(srt_path),
        "theme_hint": theme_hint,
        "max_still_duration_seconds": max_duration,
        "scene_count": len(scenes),
        "scenes": scenes,
    }
    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_scene_prompt_seed(scene_prompts_seed_path, scenes)
    beat_report_path.write_text(build_beat_report(scenes), encoding="utf-8")
    script_analysis_report_path.write_text(build_beat_report(scenes), encoding="utf-8")

    project["scene_plan"]["status"] = "completed"
    project["scene_plan"]["scene_count"] = len(scenes)
    project["scene_plan"]["original_segment_count"] = len(sentence_blocks)
    project["prompts"]["status"] = "pending"
    project.setdefault("logs", {})["beat_extraction_report_path"] = str(beat_report_path)
    project["logs"]["script_analysis_report_path"] = str(script_analysis_report_path)
    project["current_stage"] = "prompt_package"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(scene_plan_path)
    print(sentence_blocks_json_path)
    print(scene_prompts_seed_path)


if __name__ == "__main__":
    main()
