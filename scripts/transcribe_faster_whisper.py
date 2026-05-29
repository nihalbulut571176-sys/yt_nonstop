import argparse
import json
from pathlib import Path

from faster_whisper import WhisperModel


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def write_srt(segments, output_path: Path) -> None:
    lines = []
    for index, segment in enumerate(segments, start=1):
        start = format_srt_timestamp(segment["start"])
        end = format_srt_timestamp(segment["end"])
        text = segment["text"].strip()
        lines.extend([str(index), f"{start} --> {end}", text, ""])
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path")
    parser.add_argument("--model", default="base")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--initial-prompt-file", default="")
    args = parser.parse_args()

    audio_path = Path(args.audio_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    initial_prompt = ""
    if str(args.initial_prompt_file).strip():
        prompt_path = Path(args.initial_prompt_file)
        if prompt_path.exists():
            initial_prompt = prompt_path.read_text(encoding="utf-8-sig").strip()

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=args.language,
        vad_filter=True,
        beam_size=5,
        word_timestamps=False,
        initial_prompt=initial_prompt or None,
    )

    segments = []
    for segment in segments_iter:
        segments.append(
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
            }
        )

    stem = audio_path.stem
    srt_path = output_dir / f"{stem}.srt"
    json_path = output_dir / f"{stem}.segments.json"
    meta_path = output_dir / f"{stem}.meta.json"

    write_srt(segments, srt_path)
    json_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "duration_after_vad": info.duration_after_vad,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(srt_path)
    print(json_path)
    print(meta_path)


if __name__ == "__main__":
    main()
