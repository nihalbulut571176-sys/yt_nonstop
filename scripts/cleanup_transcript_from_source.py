import argparse
import json
import re
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


SENTENCE_END_RE = re.compile(r"[.!?…]$|[.!?…][\"'»”)]$")


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


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def resolve_source_text(project: dict) -> tuple[Path | None, str]:
    candidates = [
        project.get("transcript_cleanup", {}).get("source_text_path"),
        project.get("rewrite", {}).get("approved_script_path"),
        project.get("rewrite", {}).get("rewritten_script_path"),
        project.get("rewrite", {}).get("source_text_path"),
        project.get("inputs", {}).get("raw_text_path"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            text = normalize_text(path.read_text(encoding="utf-8-sig"))
            if text:
                return path, text
    return None, ""


def split_source_text_into_sentences(text: str) -> list[str]:
    text = text.replace("\r", "\n")
    chunks = re.split(r"(?<=[.!?…])\s+|\n+", text)
    sentences = [normalize_text(chunk) for chunk in chunks if normalize_text(chunk)]
    return sentences


def split_sentence_by_words(text: str, parts: int) -> list[str]:
    words = text.split()
    if parts <= 1 or len(words) <= 1:
        return [text]
    base = len(words) // parts
    remainder = len(words) % parts
    chunks = []
    cursor = 0
    for index in range(parts):
        take = base + (1 if index < remainder else 0)
        if take <= 0:
            take = 1
        next_cursor = min(len(words), cursor + take)
        chunks.append(" ".join(words[cursor:next_cursor]).strip())
        cursor = next_cursor
    if cursor < len(words):
        chunks[-1] = f"{chunks[-1]} {' '.join(words[cursor:])}".strip()
    return [chunk for chunk in chunks if chunk]


def rebalance_sentences(sentences: list[str], target_count: int) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if target_count <= 0:
        return [], warnings
    if not sentences:
        return [], warnings
    current = list(sentences)

    if len(current) < target_count:
        warnings.append("Source sentence count is lower than whisper block count; some source sentences were split.")
        while len(current) < target_count:
            longest_index = max(range(len(current)), key=lambda idx: len(current[idx].split()))
            longest = current.pop(longest_index)
            parts_needed = min(target_count - len(current), max(2, len(longest.split()) // 5))
            split_parts = split_sentence_by_words(longest, parts_needed)
            for offset, part in enumerate(split_parts):
                current.insert(longest_index + offset, part)
            if len(split_parts) == 1:
                current.insert(longest_index + 1, longest)
                break

    if len(current) > target_count:
        warnings.append("Source sentence count differs from whisper block count; some source sentences were merged to match audio timing.")
        merged: list[str] = []
        start = 0
        total = len(current)
        for bucket in range(target_count):
            end = round((bucket + 1) * total / target_count)
            if end <= start:
                end = start + 1
            merged.append(normalize_text(" ".join(current[start:end])))
            start = end
        current = merged

    if len(current) != target_count:
        warnings.append("Alignment ended with count mismatch; falling back to whisper wording for unmatched blocks.")

    return current, warnings


def build_cleaned_segments(whisper_blocks: list[dict], source_sentences: list[str]) -> list[dict]:
    cleaned = []
    for index, block in enumerate(whisper_blocks):
        text = source_sentences[index] if index < len(source_sentences) and source_sentences[index] else block["text"]
        cleaned.append(
            {
                "segment_id": index + 1,
                "start": block["start"],
                "end": block["end"],
                "start_tc": block["start_tc"],
                "end_tc": block["end_tc"],
                "duration": round(block["end"] - block["start"], 6),
                "text": normalize_text(text),
                "whisper_text": block["text"],
            }
        )
    return cleaned


def write_cleaned_srt(path: Path, segments: list[dict]) -> None:
    lines = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                f"{format_srt_timestamp(segment['start'])} --> {format_srt_timestamp(segment['end'])}",
                segment["text"],
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_cleaned_transcript_md(path: Path, segments: list[dict]) -> None:
    lines = ["# Cleaned Timed Transcript", ""]
    for segment in segments:
        lines.append(f"- [{segment['start_tc']} - {segment['end_tc']}] {segment['text']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)

    srt_path = Path(project["transcription"]["srt_path"])
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT not found: {srt_path}")

    source_path, source_text = resolve_source_text(project)
    cleanup_report_path = Path(project["transcript_cleanup"]["cleanup_report_path"])
    timing_cleanup_report_path = Path(project["logs"]["timing_cleanup_report_path"])
    cleaned_srt_path = Path(project["transcript_cleanup"]["cleaned_srt_path"])
    cleaned_segments_json_path = Path(project["transcript_cleanup"]["cleaned_segments_json_path"])
    cleaned_md_path = Path(project["transcript_cleanup"]["cleaned_timed_transcript_md_path"])

    whisper_segments = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
    whisper_blocks = merge_into_sentence_blocks(whisper_segments)
    meta_path = Path(project["transcription"]["meta_json_path"])
    meta = load_json(meta_path) if meta_path.exists() else {}

    if not source_text:
        report = {
            "project_id": project["project_id"],
            "source_language": project["meta"].get("language", "auto"),
            "whisper_language": meta.get("language"),
            "source_sentence_count": 0,
            "whisper_segment_count": len(whisper_blocks),
            "aligned_segment_count": len(whisper_blocks),
            "status": "warning",
            "warnings": [
                "No source script found. Scene plan will be built from raw Whisper transcript."
            ],
        }
        save_json(cleanup_report_path, report)
        timing_cleanup_report_path.write_text(
            "# Timing Cleanup Report\n\nStatus: warning\n\n- No source script found. Scene plan will be built from raw Whisper transcript.\n",
            encoding="utf-8",
        )
        project["transcript_cleanup"]["status"] = "skipped_no_source"
        project["transcript_cleanup"]["used_source_path"] = None
        project["scene_plan"]["source_srt_path"] = str(srt_path)
        save_project(project_json, project)
        print(cleanup_report_path)
        return

    source_sentences = split_source_text_into_sentences(source_text)
    rebalanced_sentences, warnings = rebalance_sentences(source_sentences, len(whisper_blocks))
    cleaned_segments = build_cleaned_segments(whisper_blocks, rebalanced_sentences)

    cleaned_srt_path.parent.mkdir(parents=True, exist_ok=True)
    write_cleaned_srt(cleaned_srt_path, cleaned_segments)
    save_json(cleaned_segments_json_path, cleaned_segments)
    write_cleaned_transcript_md(cleaned_md_path, cleaned_segments)

    status = "passed" if not warnings and len(source_sentences) == len(whisper_blocks) else "warning"
    report = {
        "project_id": project["project_id"],
        "source_language": project["meta"].get("language", "auto"),
        "whisper_language": meta.get("language"),
        "source_sentence_count": len(source_sentences),
        "whisper_segment_count": len(whisper_blocks),
        "aligned_segment_count": len(cleaned_segments),
        "status": status,
        "warnings": warnings,
    }
    save_json(cleanup_report_path, report)
    timing_cleanup_report_path.write_text(
        "\n".join(
            [
                "# Timing Cleanup Report",
                "",
                f"Status: {status}",
                f"Source sentence count: {len(source_sentences)}",
                f"Whisper segment count: {len(whisper_blocks)}",
                f"Aligned segment count: {len(cleaned_segments)}",
                "",
                "Warnings:",
                *(warnings or ["- none"]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    project["transcript_cleanup"]["status"] = "completed" if status == "passed" else "warning"
    project["transcript_cleanup"]["used_source_path"] = str(source_path) if source_path else None
    project["scene_plan"]["source_srt_path"] = str(cleaned_srt_path)
    project["current_stage"] = "scene_plan"
    save_project(project_json, project)

    print(cleaned_srt_path)
    print(cleaned_segments_json_path)
    print(cleanup_report_path)


if __name__ == "__main__":
    main()
