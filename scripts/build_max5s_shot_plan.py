import json
import math
import re
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
TIMELINE_JSON = ROOT / "edit" / "timeline.json"
PROMPTS_MD = ROOT / "deliverables" / "sentence_visual_prompts_generator_ready.md"
NORMALIZED_IMAGES_DIR = ROOT / "edit" / "normalized_images"
EXTRA_IMAGES_DIR = ROOT / "edit" / "normalized_extra_images"
OUT_DIR = ROOT / "edit"
MAX_DURATION = 5.0
EXTRA_START_INDEX = 189

VARIANT_CUES = [
    "same scene and subject continuity, alternate camera angle, tighter composition",
    "same scene and subject continuity, wider environmental composition, stronger sense of scale",
    "same scene and subject continuity, detail-focused insert shot, secondary visual emphasis",
    "same scene and subject continuity, side-angle composition, fresh perspective",
    "same scene and subject continuity, overhead or elevated composition, structural emphasis",
]


def parse_prompt_blocks(path: Path) -> list[str]:
    return [block.strip() for block in path.read_text(encoding="utf-8").split("\n\n") if block.strip()]


def split_prompt(block: str) -> tuple[str, str]:
    if block.startswith("No character reference. "):
        return "No character reference. ", block[len("No character reference. ") :].strip()
    multi = re.match(r"(Use reference images:\s+[A-Za-z0-9_,\s]+\.\s+)(.*)$", block, re.S)
    if multi:
        return multi.group(1), multi.group(2).strip()
    single = re.match(r"(Use reference image:\s+[A-Za-z0-9_]+\.\s+)(.*)$", block, re.S)
    if single:
        return single.group(1), single.group(2).strip()
    raise ValueError(f"Unrecognized prompt block: {block[:120]}")


def inject_variant(body: str, variant_cue: str) -> str:
    suffix = ", no text"
    if body.endswith(suffix):
        return body[: -len(suffix)] + f", {variant_cue}{suffix}"
    return body + f", {variant_cue}"


def split_duration(total: float, parts: int) -> list[float]:
    base = total / parts
    durations = [round(base, 6) for _ in range(parts)]
    correction = round(total - sum(durations), 6)
    durations[-1] = round(durations[-1] + correction, 6)
    return durations


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EXTRA_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    timeline = json.loads(TIMELINE_JSON.read_text(encoding="utf-8"))
    prompts = parse_prompt_blocks(PROMPTS_MD)

    if len(timeline) != len(prompts):
        raise RuntimeError(f"Timeline/prompts length mismatch: {len(timeline)} vs {len(prompts)}")

    shot_plan = []
    extra_prompt_blocks = []
    long_segments = []
    next_extra_index = EXTRA_START_INDEX

    for item, block in zip(timeline, prompts):
        prefix, prompt_body = split_prompt(block)
        parts = int(math.ceil(float(item["duration"]) / MAX_DURATION))
        durations = split_duration(float(item["duration"]), parts)

        if parts > 1:
            long_segments.append(
                {
                    "source_index": item["index"],
                    "start": item["start"],
                    "end": item["end"],
                    "original_duration": item["duration"],
                    "parts": parts,
                }
            )

        cursor = float(item["start"])
        for part_idx in range(parts):
            duration = durations[part_idx]
            shot_start = round(cursor, 6)
            shot_end = round(cursor + duration, 6)
            cursor = shot_end

            if part_idx == 0:
                image_path = NORMALIZED_IMAGES_DIR / f"{item['index']:03d}.png"
                prompt_block = block
                source_kind = "original"
                generated_index = item["index"]
            else:
                generated_index = next_extra_index
                next_extra_index += 1
                variant_cue = VARIANT_CUES[(part_idx - 1) % len(VARIANT_CUES)]
                variant_body = inject_variant(prompt_body, variant_cue)
                prompt_block = prefix + variant_body
                extra_prompt_blocks.append(prompt_block)
                image_path = EXTRA_IMAGES_DIR / f"{generated_index:03d}.png"
                source_kind = "extra"

            shot_plan.append(
                {
                    "shot_index": len(shot_plan) + 1,
                    "source_index": item["index"],
                    "generated_index": generated_index,
                    "part_index": part_idx + 1,
                    "parts_total": parts,
                    "start": shot_start,
                    "end": shot_end,
                    "duration": duration,
                    "image": str(image_path),
                    "source_kind": source_kind,
                    "text": item["text"],
                    "prompt": prompt_block,
                }
            )

    (OUT_DIR / "long_segment_report.json").write_text(
        json.dumps(
            {
                "max_duration_seconds": MAX_DURATION,
                "original_segments": len(timeline),
                "long_segments": len(long_segments),
                "extra_prompts_needed": len(extra_prompt_blocks),
                "final_shot_count": len(shot_plan),
                "segments": long_segments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT_DIR / "shot_plan_max5.json").write_text(json.dumps(shot_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "extra_prompts_max5.md").write_text("\n\n".join(extra_prompt_blocks) + "\n", encoding="utf-8")

    print(OUT_DIR / "long_segment_report.json")
    print(OUT_DIR / "shot_plan_max5.json")
    print(OUT_DIR / "extra_prompts_max5.md")


if __name__ == "__main__":
    main()
