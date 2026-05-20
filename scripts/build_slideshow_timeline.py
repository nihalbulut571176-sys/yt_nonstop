import json
import re
from pathlib import Path


SENTENCE_BLOCKS = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_blocks_from_srt.txt")
IMAGES_DIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\fastgen_run\images")
AUDIO_META = Path(r"C:\Users\MIKE\Documents\Codex\YT\transcript_fw\message@elevenLabsVoicerBot.meta.json")
OUT_DIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\edit")
NORMALIZED_IMAGES_DIR = OUT_DIR / "normalized_images"
SHOT_PLAN = OUT_DIR / "shot_plan_max5.json"


def parse_timecode(tc: str) -> float:
    hh, mm, rest = tc.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if SHOT_PLAN.exists():
        shot_entries = json.loads(SHOT_PLAN.read_text(encoding="utf-8"))
        ffconcat_path = OUT_DIR / "timeline.ffconcat"
        ffconcat_lines = ["ffconcat version 1.0"]
        for item in shot_entries:
            image_path = Path(item["image"])
            if not image_path.exists():
                raise FileNotFoundError(f"Missing image: {image_path}")
            safe_path = str(image_path).replace("\\", "/").replace("'", r"'\''")
            ffconcat_lines.append(f"file '{safe_path}'")
            ffconcat_lines.append(f"duration {float(item['duration']):.6f}")
        final_safe = str(Path(shot_entries[-1]["image"])).replace("\\", "/").replace("'", r"'\''")
        ffconcat_lines.append(f"file '{final_safe}'")
        ffconcat_path.write_text("\n".join(ffconcat_lines) + "\n", encoding="utf-8")

        timeline_json = OUT_DIR / "timeline.json"
        timeline_json.write_text(json.dumps(shot_entries, ensure_ascii=False, indent=2), encoding="utf-8")
        print(ffconcat_path)
        print(timeline_json)
        return

    lines = [line.strip() for line in SENTENCE_BLOCKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = json.loads(AUDIO_META.read_text(encoding="utf-8"))
    audio_duration = float(meta["duration"])

    entries = []
    pattern = re.compile(r"^(\d+)\.\s+\[(.*?)\s+-\s+(.*?)\]\s+(.*)$")
    for line in lines:
        m = pattern.match(line)
        if not m:
            raise ValueError(f"Unrecognized sentence block line: {line}")
        idx = int(m.group(1))
        start = parse_timecode(m.group(2))
        end = parse_timecode(m.group(3))
        text = m.group(4)
        normalized_path = NORMALIZED_IMAGES_DIR / f"{idx:03d}.png"
        image_path = normalized_path if normalized_path.exists() else IMAGES_DIR / f"{idx:03d}.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Missing image: {image_path}")
        entries.append(
            {
                "index": idx,
                "start": start,
                "end": end,
                "duration": max(0.04, end - start),
                "image": str(image_path),
                "text": text,
            }
        )

    if not entries:
        raise RuntimeError("No timeline entries found")

    last = entries[-1]
    last["duration"] = max(last["duration"], audio_duration - last["start"])

    ffconcat_path = OUT_DIR / "timeline.ffconcat"
    ffconcat_lines = ["ffconcat version 1.0"]
    for item in entries:
        safe_path = item["image"].replace("\\", "/").replace("'", r"'\''")
        ffconcat_lines.append(f"file '{safe_path}'")
        ffconcat_lines.append(f"duration {item['duration']:.6f}")
    final_safe = entries[-1]["image"].replace("\\", "/").replace("'", r"'\''")
    ffconcat_lines.append(f"file '{final_safe}'")
    ffconcat_path.write_text("\n".join(ffconcat_lines) + "\n", encoding="utf-8")

    timeline_json = OUT_DIR / "timeline.json"
    timeline_json.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    print(ffconcat_path)
    print(timeline_json)


if __name__ == "__main__":
    main()
