import argparse
import importlib.util
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


def parse_timecode(tc: str) -> float:
    hh, mm, rest = tc.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def load_xlsx_rows(workspace_root: Path, xlsx_path: Path) -> list[dict]:
    helper_path = workspace_root / "scripts" / "generate_master_test_batch_parallel.py"
    spec = importlib.util.spec_from_file_location("generate_master_test_batch_parallel", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load workbook reader from {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_xlsx_sheet_objects(xlsx_path, "Generation_Master")


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--xlsx-path", required=True)
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--run-name", default="")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    project_root = Path(args.project_root).resolve()
    xlsx_path = Path(args.xlsx_path).resolve()
    images_dir = Path(args.images_dir).resolve()
    audio_path = Path(args.audio_path).resolve()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or f"master645_timed_montage_{timestamp}"
    run_root = project_root / "video_runs" / run_name
    clips_dir = run_root / "clips"
    timeline_dir = run_root / "timeline"
    exports_dir = run_root / "exports"
    logs_dir = run_root / "logs"
    for directory in [clips_dir, timeline_dir, exports_dir, logs_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    rows = load_xlsx_rows(workspace_root, xlsx_path)
    audio_duration = ffprobe_duration(audio_path)

    timeline = []
    concat_lines = ["ffconcat version 1.0"]
    for row_index, row in enumerate(rows, start=1):
        image_path = images_dir / f"scene_{row_index:04d}_V01.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Missing generated image for row {row_index}: {image_path}")

        start = parse_timecode(row["start_time"])
        end = parse_timecode(row["end_time"])
        if row_index == len(rows):
            end = min(end, audio_duration)
        duration = round(max(0.04, end - start), 6)
        direction = "right" if row_index % 2 else "left"
        clip_path = clips_dir / f"{row_index:04d}.mp4"
        render_clip(image_path, clip_path, duration, direction)
        concat_lines.append(f"file '{safe_ffconcat_path(clip_path)}'")
        timeline.append(
            {
                "row_index": row_index,
                "master_id": row["id"],
                "section": row.get("section", ""),
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": duration,
                "voiceover_excerpt": row.get("voiceover_excerpt", ""),
                "visual_function": row.get("visual_function", ""),
                "visual_strategy": row.get("visual_strategy", ""),
                "shot_type": row.get("shot_type", ""),
                "image": str(image_path),
                "clip": str(clip_path),
                "movement": f"pan_{direction}",
                "zoom_used": False,
            }
        )

    ffconcat_path = timeline_dir / "timeline.ffconcat"
    ffconcat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    timeline_json_path = timeline_dir / "timeline.json"
    timeline_json_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    output_path = exports_dir / "final_video_from_generated_images_timed.mp4"
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
        "xlsx_first_start": rows[0]["start_time"],
        "xlsx_last_end": rows[-1]["end_time"],
        "timeline_path": str(timeline_json_path),
        "ffconcat_path": str(ffconcat_path),
        "output_path": str(output_path),
        "motion_rule": "horizontal pan only, alternating left/right, no zoom",
    }
    (logs_dir / "render_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (logs_dir / "render_report.md").write_text(
        "\n".join(
            [
                "# Render Report",
                "",
                f"- Master rows: {len(rows)}",
                f"- Audio duration seconds: {audio_duration}",
                f"- Master first start: {rows[0]['start_time']}",
                f"- Master last end: {rows[-1]['end_time']}",
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
