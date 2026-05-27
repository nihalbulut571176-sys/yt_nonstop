import argparse
import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path


FPS = 30
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
WORK_WIDTH = 2048
WORK_HEIGHT = 1152


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def safe_ffconcat_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", r"'\''")


def render_clip(image_path: Path, clip_path: Path, duration: float, direction: str) -> None:
    travel = WORK_WIDTH - OUTPUT_WIDTH
    safe_duration = max(duration, 0.2)
    if direction == "right":
        x_expr = f"({travel})*(t/{safe_duration:.6f})"
    else:
        x_expr = f"({travel})*(1-t/{safe_duration:.6f})"
    y_expr = f"({WORK_HEIGHT}-{OUTPUT_HEIGHT})/2"
    vf = (
        f"scale={WORK_WIDTH}:{WORK_HEIGHT}:flags=lanczos,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:x='{x_expr}':y='{y_expr}',"
        f"fps={FPS},format=yuv420p"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            f"{duration:.6f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            str(clip_path),
        ]
    )


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    if not rows:
        raise RuntimeError(f"No rows found in {csv_path}")
    return rows


def first_present(row: dict, keys: list[str], *, required: bool = True, default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text != "":
            return text
    if required:
        raise KeyError(f"Missing required CSV column value. Tried: {', '.join(keys)}")
    return default


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--run-name", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    csv_path = Path(args.csv_path).resolve()
    images_dir = Path(args.images_dir).resolve()
    audio_path = Path(args.audio_path).resolve()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or f"automontage_csv_render_{timestamp}"
    run_root = project_root / "video_runs" / run_name
    clips_dir = run_root / "clips"
    timeline_dir = run_root / "timeline"
    exports_dir = run_root / "exports"
    logs_dir = run_root / "logs"
    for directory in [clips_dir, timeline_dir, exports_dir, logs_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    rows = load_rows(csv_path)
    audio_duration = ffprobe_duration(audio_path)

    timeline = []
    concat_lines = ["ffconcat version 1.0"]

    for row in rows:
        seq = int(first_present(row, ["timeline_order", "sequence_index", "prompt_index_original"]))
        image_path = images_dir / f"scene_{seq:04d}_V01.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Missing generated image for sequence {seq}: {image_path}")

        start = float(first_present(row, ["image_in_point_sec", "start_sec"]))
        end = float(first_present(row, ["image_out_point_sec", "end_sec"]))
        duration = round(max(0.04, end - start), 6)
        direction = "right" if seq % 2 else "left"
        clip_path = clips_dir / f"{seq:04d}.mp4"
        render_clip(image_path, clip_path, duration, direction)
        concat_lines.append(f"file '{safe_ffconcat_path(clip_path)}'")
        timeline.append(
            {
                "sequence_index": seq,
                "asset_name": first_present(row, ["asset_name", "image_filename"], required=False, default=f"scene_{seq:04d}"),
                "beat_id": first_present(row, ["prompt_id", "beat_id"], required=False, default=f"scene_{seq:04d}"),
                "section": first_present(row, ["section"], required=False, default=""),
                "start": start,
                "end": end,
                "duration": duration,
                "subtitle_index_start": first_present(row, ["srt_subtitle_index_start", "subtitle_index_start"], required=False, default=""),
                "subtitle_index_end": first_present(row, ["srt_subtitle_index_end", "subtitle_index_end"], required=False, default=""),
                "voiceover_excerpt": first_present(row, ["voiceover_excerpt_prompt", "voiceover_excerpt"], required=False, default=""),
                "prompt_tier": first_present(row, ["preferred_prompt_tier", "prompt_tier"], required=False, default=""),
                "timing_source": "image_in_point_sec/image_out_point_sec" if row.get("image_in_point_sec") else "start_sec/end_sec",
                "image": str(image_path),
                "clip": str(clip_path),
                "movement": f"pan_{direction}",
                "zoom_used": False,
            }
        )

    if timeline[0]["start"] > 0.001:
        raise RuntimeError(f"Timeline starts late at {timeline[0]['start']:.3f}s")
    for previous, current in zip(timeline, timeline[1:]):
        if current["start"] + 0.001 < previous["end"]:
            raise RuntimeError(
                f"Timeline overlap between sequence {previous['sequence_index']} and {current['sequence_index']}: "
                f"{previous['end']:.3f}s -> {current['start']:.3f}s"
            )
    timeline_end = timeline[-1]["end"]

    ffconcat_path = timeline_dir / "timeline.ffconcat"
    ffconcat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    timeline_json_path = timeline_dir / "timeline.json"
    timeline_json_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    output_path = exports_dir / "final_video_from_automontage_csv.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(ffconcat_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]
    )

    report = {
        "row_count": len(rows),
        "audio_duration_seconds": audio_duration,
        "timeline_end_seconds": timeline_end,
        "csv_path": str(csv_path),
        "timeline_path": str(timeline_json_path),
        "ffconcat_path": str(ffconcat_path),
        "output_path": str(output_path),
        "timing_columns_used": ["image_in_point_sec", "image_out_point_sec"] if rows[0].get("image_in_point_sec") else ["start_sec", "end_sec"],
        "old_prompt_time_columns_ignored": ["old_prompt_start_time_DO_NOT_USE", "old_prompt_end_time_DO_NOT_USE"],
        "motion_rule": "horizontal pan only, alternating left/right, no zoom",
    }
    (logs_dir / "render_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (logs_dir / "render_report.md").write_text(
        "\n".join(
            [
                "# Render Report",
                "",
                f"- CSV rows: {len(rows)}",
                f"- Audio duration seconds: {audio_duration}",
                f"- CSV source: {csv_path}",
                "- Motion rule: horizontal pan only, alternating left/right, no zoom animation",
                f"- Timeline: {timeline_json_path}",
                f"- FFconcat: {ffconcat_path}",
                f"- Output: {output_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
