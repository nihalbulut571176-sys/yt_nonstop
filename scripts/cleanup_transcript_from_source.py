import argparse
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
SPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


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
                "id": len(segments) + 1,
                "start_tc": start_tc,
                "end_tc": end_tc,
                "start": parse_srt_timestamp(start_tc),
                "end": parse_srt_timestamp(end_tc),
                "text": SPACE_RE.sub(" ", content).strip(),
            }
        )
    return segments


def normalize_text(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    lowered = PUNCT_RE.sub(" ", lowered)
    return SPACE_RE.sub(" ", lowered).strip()


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [token for token in normalized.split(" ") if token]


def split_source_sentences(text: str) -> list[str]:
    flattened = SPACE_RE.sub(" ", text.replace("\n", " ")).strip()
    if not flattened:
        return []
    parts = SENTENCE_SPLIT_RE.split(flattened)
    sentences = [part.strip() for part in parts if part.strip()]
    return sentences or [flattened]


def read_source_text(project: dict) -> tuple[Path | None, str]:
    candidates = [
        project.get("rewrite", {}).get("approved_script_path"),
        project.get("rewrite", {}).get("rewritten_script_path"),
        project.get("rewrite", {}).get("source_text_path"),
        project.get("inputs", {}).get("raw_text_path"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8-sig").strip()
        if text:
            return path, text
    return None, ""


def join_sentences(sentences: list[str], start: int, count: int) -> str:
    return " ".join(sentence.strip() for sentence in sentences[start : start + count]).strip()


def similarity_score(source_text: str, whisper_text: str) -> float:
    normalized_source = normalize_text(source_text)
    normalized_whisper = normalize_text(whisper_text)
    if not normalized_source or not normalized_whisper:
        return 0.0
    ratio = SequenceMatcher(None, normalized_source, normalized_whisper).ratio()
    source_tokens = set(tokenize(source_text))
    whisper_tokens = set(tokenize(whisper_text))
    overlap = len(source_tokens & whisper_tokens)
    token_score = overlap / max(1, len(whisper_tokens))
    return ratio * 0.75 + token_score * 0.25


def align_sentences_to_segments(source_sentences: list[str], whisper_segments: list[dict]) -> list[int]:
    sentence_count = len(source_sentences)
    segment_count = len(whisper_segments)
    if sentence_count < segment_count:
        raise RuntimeError(
            f"Source has fewer sentences ({sentence_count}) than ASR segments ({segment_count}); cannot assign at least one sentence per segment."
        )

    max_group = max(1, min(6, sentence_count - segment_count + 1))
    penalty = 10**9
    dp: list[list[float]] = [[penalty] * (segment_count + 1) for _ in range(sentence_count + 1)]
    choice: list[list[int]] = [[0] * (segment_count + 1) for _ in range(sentence_count + 1)]
    dp[sentence_count][segment_count] = 0.0

    for sentence_index in range(sentence_count - 1, -1, -1):
        for segment_index in range(segment_count - 1, -1, -1):
            remaining_sentences = sentence_count - sentence_index
            remaining_segments = segment_count - segment_index
            min_take = 1
            max_take = min(max_group, remaining_sentences - (remaining_segments - 1))
            if max_take < min_take:
                continue
            best_cost = penalty
            best_take = 1
            for take in range(min_take, max_take + 1):
                joined = join_sentences(source_sentences, sentence_index, take)
                score = similarity_score(joined, whisper_segments[segment_index]["text"])
                length_gap = abs(len(normalize_text(joined)) - len(normalize_text(whisper_segments[segment_index]["text"])))
                cost = (1.0 - score) * 100 + length_gap * 0.02 + dp[sentence_index + take][segment_index + 1]
                if cost < best_cost:
                    best_cost = cost
                    best_take = take
            dp[sentence_index][segment_index] = best_cost
            choice[sentence_index][segment_index] = best_take

    assignments = []
    sentence_index = 0
    for segment_index in range(segment_count):
        take = choice[sentence_index][segment_index]
        if take <= 0:
            raise RuntimeError("Failed to align source sentences to ASR segments.")
        assignments.append(take)
        sentence_index += take
    if sentence_index != sentence_count:
        raise RuntimeError("Alignment did not consume all source sentences.")
    return assignments


def write_cleaned_srt(path: Path, cleaned_segments: list[dict]) -> None:
    blocks = []
    for index, item in enumerate(cleaned_segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{item['start_tc']} --> {item['end_tc']}",
                    item["text"],
                ]
            )
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_timed_transcript(path: Path, cleaned_segments: list[dict]) -> None:
    lines = ["# Cleaned Timed Transcript", ""]
    for item in cleaned_segments:
        lines.append(f"- [{item['start_tc']} - {item['end_tc']}] {item['text']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_timing_report(path: Path, report: dict) -> None:
    warnings = report.get("warnings", [])
    lines = [
        "# Timing Cleanup Report",
        "",
        f"Status: {report['status']}",
        f"Source sentence count: {report['source_sentence_count']}",
        f"Whisper segment count: {report['whisper_segment_count']}",
        f"Aligned segment count: {report['aligned_segment_count']}",
        "",
        "Method:",
        "Source text was aligned onto raw ASR segment timings in order.",
        "",
        "Warnings:",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    transcript_info = project["transcript_cleanup"]
    source_path, source_text = read_source_text(project)
    if not source_text:
        raise FileNotFoundError("No non-empty source voiceover text file found for transcript cleanup.")

    raw_srt_path = Path(project["transcription"]["srt_path"])
    if not raw_srt_path.exists():
        raise FileNotFoundError(f"Raw transcription SRT not found: {raw_srt_path}")

    whisper_segments = parse_srt(raw_srt_path.read_text(encoding="utf-8-sig"))
    source_sentences = split_source_sentences(source_text)
    assignments = align_sentences_to_segments(source_sentences, whisper_segments)

    cleaned_segments = []
    sentence_index = 0
    for whisper_segment, take in zip(whisper_segments, assignments, strict=True):
        text = join_sentences(source_sentences, sentence_index, take)
        sentence_index += take
        cleaned_segments.append(
            {
                "segment_id": len(cleaned_segments) + 1,
                "start": whisper_segment["start"],
                "end": whisper_segment["end"],
                "start_tc": whisper_segment["start_tc"],
                "end_tc": whisper_segment["end_tc"],
                "duration": round(whisper_segment["end"] - whisper_segment["start"], 6),
                "text": text,
                "whisper_text": whisper_segment["text"],
            }
        )

    warnings = []
    if len(source_sentences) != len(whisper_segments):
        warnings.append(
            "Source sentence count differs from whisper block count; source sentences were grouped onto raw ASR timings."
        )

    cleaned_srt_path = Path(transcript_info["cleaned_srt_path"])
    cleaned_segments_path = Path(transcript_info["cleaned_segments_json_path"])
    timed_transcript_path = Path(transcript_info["cleaned_timed_transcript_md_path"])
    cleanup_report_path = Path(transcript_info["cleanup_report_path"])

    write_cleaned_srt(cleaned_srt_path, cleaned_segments)
    cleaned_segments_path.write_text(json.dumps(cleaned_segments, ensure_ascii=False, indent=2), encoding="utf-8")
    write_timed_transcript(timed_transcript_path, cleaned_segments)

    report = {
        "project_id": project["project_id"],
        "source_language": project["meta"].get("language", "unknown"),
        "whisper_language": project["transcription"].get("requested_language", "unknown"),
        "source_sentence_count": len(source_sentences),
        "whisper_segment_count": len(whisper_segments),
        "aligned_segment_count": len(cleaned_segments),
        "status": "warning" if warnings else "success",
        "warnings": warnings,
        "source_text_path": str(source_path) if source_path else None,
        "raw_srt_path": str(raw_srt_path),
        "method": "raw_asr_timings_with_source_text",
    }
    cleanup_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    timing_report_path = Path(project.get("logs", {}).get("timing_cleanup_report_path", ""))
    if timing_report_path:
        timing_report_path.parent.mkdir(parents=True, exist_ok=True)
        write_timing_report(timing_report_path, report)

    project["transcript_cleanup"]["status"] = report["status"]
    project["transcript_cleanup"]["used_source_path"] = str(source_path) if source_path else project["transcript_cleanup"].get("used_source_path")
    project["scene_plan"]["source_srt_path"] = str(cleaned_srt_path)
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(cleaned_srt_path)
    print(cleaned_segments_path)
    print(timed_transcript_path)
    print(cleanup_report_path)


if __name__ == "__main__":
    main()
