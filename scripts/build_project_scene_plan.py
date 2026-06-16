import argparse
import json
import math
import re
from pathlib import Path

from project_pipeline_utils import iso_now, load_project, save_project
from yt_nonstop.utils.text_repair import repair_mojibake_text


SENTENCE_END_RE = re.compile(r"[.!?…]$|[.!?…][\"')\]]$")
VISUAL_FUNCTIONS = [
    "hook",
    "explain",
    "evidence",
    "emotion",
    "transition",
    "contrast",
    "pattern_break",
    "payoff",
]
VISUAL_STRATEGIES = [
    "literal_premium",
    "mechanism_view",
    "human_consequence",
    "evidence_wall",
    "scale_contrast",
    "emotional_metaphor",
    "before_after_contrast",
    "tension_detail",
]


def parse_srt_timestamp(tc: str) -> float:
    hh, mm, rest = tc.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def parse_srt(text: str) -> list[dict]:
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        start_tc, end_tc = lines[1].split(" --> ")
        content = repair_mojibake_text(" ".join(line.strip() for line in lines[2:]))
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


def default_scene_fields(voice_text: str, shot_index: int) -> dict:
    return {
        "scene_summary": voice_text,
        "scene_meaning": "",
        "narrative_purpose": "",
        "viewer_emotion": "",
        "tension_level": 0,
        "curiosity_hook": "",
        "information_density": "medium",
        "retention_risk": "unknown",
        "visual_need": "pending",
        "visual_function": "hook" if shot_index <= 3 else "",
        "visual_strategy": "",
        "visual_idea": "",
        "main_subject": "",
        "environment": "",
        "composition": "",
        "mood": "",
        "visual_reason": "",
        "internal_beats": [],
        "event_clarity_required": False,
        "event_type": "",
        "event_priority_reason": "",
        "visual_goal": "",
        "draft_prompt": "",
        "final_prompt": "",
        "prompt": "",
        "motion_id": "",
        "motion_plan": {},
        "scene_importance": "opening" if shot_index <= 6 else "standard",
        "shot_id": "",
        "source_shot_id": "",
        "generation_mode": "unique",
        "variation_note": "",
        "shot_role": "",
        "primary_subject": "",
        "secondary_subjects": [],
        "what_is_in_frame": "",
        "camera": "",
        "lighting": "",
        "negative_prompt": "",
        "continuity_notes": "",
        "qa_status": {
            "scene_qa": "pending",
            "prompt_qa": "pending",
            "final_review": "pending",
        },
        "quality_target": 9.0 if shot_index <= 8 else 8.5,
    }


def build_scene_plan(sentence_blocks: list[dict], max_duration: float) -> tuple[list[dict], list[dict]]:
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
            shot_index = len(scenes) + 1

            scene = {
                "scene_id": f"scene_{shot_index:04d}",
                "shot_index": shot_index,
                "source_segment_id": block["segment_id"],
                "source_index": block["segment_id"],
                "part_index": idx,
                "parts_total": parts,
                "start": part_start,
                "end": part_end,
                "duration": round(part_duration, 6),
                "voice_text": block["text"],
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
                "notes": ["Prompt pending", "Still image pending"],
            }
            scene.update(default_scene_fields(block["text"], shot_index))
            scenes.append(scene)

    return scenes, long_segments


def write_sentence_block_text(path: Path, blocks: list[dict]) -> None:
    lines = [f"{item['segment_id']}. [{item['start_tc']} - {item['end_tc']}] {item['text']}" for item in blocks]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_scene_prompt_seed(path: Path, scenes: list[dict]) -> None:
    blocks = []
    for scene in scenes:
        blocks.append(
            "\n".join(
                [
                    f"Scene {scene['shot_index']} ({scene['start']:.3f}-{scene['end']:.3f}s)",
                    f"Voice text: {scene['voice_text']}",
                    "Narrative purpose:",
                    "Visual goal:",
                    "Prompt:",
                ]
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    srt_path = Path(project["scene_plan"]["source_srt_path"] or project["transcription"]["srt_path"])
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT not found: {srt_path}")

    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan_dir = scene_plan_path.parent
    scene_plan_dir.mkdir(parents=True, exist_ok=True)

    max_duration = float(project["scene_plan"]["max_still_duration_seconds"])
    segments = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
    sentence_blocks = merge_into_sentence_blocks(segments)
    scenes, long_segments = build_scene_plan(sentence_blocks, max_duration)

    sentence_blocks_json_path = scene_plan_dir / "sentence_blocks.json"
    sentence_blocks_txt_path = scene_plan_dir / "sentence_blocks.txt"
    long_segment_report_path = Path(project["scene_plan"]["long_segment_report_path"])
    scene_prompts_seed_path = Path(project["prompts"]["prompt_export_path"])

    sentence_blocks_json_path.write_text(json.dumps(sentence_blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    write_sentence_block_text(sentence_blocks_txt_path, sentence_blocks)
    long_segment_report_path.parent.mkdir(parents=True, exist_ok=True)
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

    cleaned_srt_path = Path(project["transcript_cleanup"]["cleaned_srt_path"])
    canonical_source = "cleaned.srt" if cleaned_srt_path.exists() and cleaned_srt_path == srt_path else "raw_whisper.srt"
    scene_plan = {
        "project_id": project["project_id"],
        "schema_version": project["schema_version"],
        "created_at": iso_now(),
        "source_srt_path": str(srt_path),
        "canonical_timing_source": canonical_source,
        "max_still_duration_seconds": max_duration,
        "timing_locked": False,
        "scene_qa_status": "pending",
        "prompt_qa_status": "pending",
        "final_review_status": "pending",
        "allowed_visual_functions": VISUAL_FUNCTIONS,
        "allowed_visual_strategies": VISUAL_STRATEGIES,
        "scene_count": len(scenes),
        "scenes": scenes,
    }
    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_scene_prompt_seed(scene_prompts_seed_path, scenes)

    project["scene_plan"]["status"] = "completed"
    project["scene_plan"]["scene_count"] = len(scenes)
    project["scene_plan"]["original_segment_count"] = len(sentence_blocks)
    project["prompts"]["status"] = "pending"
    project["current_stage"] = "scene_qa"
    save_project(project_json, project)

    print(scene_plan_path)
    print(sentence_blocks_json_path)
    print(scene_prompts_seed_path)


if __name__ == "__main__":
    main()
