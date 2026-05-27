import argparse
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
    if direction == "right":
        x_expr = f"({travel})*(t/{duration:.6f})"
    else:
        x_expr = f"({travel})*(1-t/{duration:.6f})"
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
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--run-name", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    images_dir = Path(args.images_dir).resolve()
    audio_path = Path(args.audio_path).resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or f"master645_images_montage_{timestamp}"
    run_root = project_root / "video_runs" / run_name
    clips_dir = run_root / "clips"
    timeline_dir = run_root / "timeline"
    exports_dir = run_root / "exports"
    logs_dir = run_root / "logs"
    for directory in [clips_dir, timeline_dir, exports_dir, logs_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    images = sorted(images_dir.glob("scene_*_V01.png"))
    if not images:
        raise RuntimeError(f"No images found in {images_dir}")

    audio_duration = ffprobe_duration(audio_path)
    base_duration = audio_duration / len(images)

    timeline = []
    concat_lines = ["ffconcat version 1.0"]
    clip_paths: list[Path] = []
    cursor = 0.0

    for index, image_path in enumerate(images, start=1):
        is_last = index == len(images)
        start = round(cursor, 6)
        duration = round(audio_duration - cursor, 6) if is_last else round(base_duration, 6)
        end = round(start + duration, 6)
        cursor = end
        direction = "right" if index % 2 else "left"
        clip_path = clips_dir / f"{index:04d}.mp4"
        render_clip(image_path, clip_path, duration, direction)
        clip_paths.append(clip_path)
        concat_lines.append(f"file '{safe_ffconcat_path(clip_path)}'")
        timeline.append(
            {
                "shot_index": index,
                "scene_id": image_path.stem.replace("_V01", ""),
                "image": str(image_path),
                "clip": str(clip_path),
                "start": start,
                "end": end,
                "duration": duration,
                "movement": f"pan_{direction}",
                "scale_mode": f"{WORK_WIDTH}x{WORK_HEIGHT}_crop_to_{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            }
        )

    ffconcat_path = timeline_dir / "timeline.ffconcat"
    ffconcat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    timeline_json_path = timeline_dir / "timeline.json"
    timeline_json_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    output_path = exports_dir / "final_video_from_generated_images.mp4"
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

    qa = {
        "image_count": len(images),
        "audio_duration_seconds": audio_duration,
        "average_image_duration_seconds": base_duration,
        "timeline_path": str(timeline_json_path),
        "ffconcat_path": str(ffconcat_path),
        "output_path": str(output_path),
        "movements": ["pan_right", "pan_left"],
        "zoom_used": False,
    }
    (logs_dir / "render_report.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    (logs_dir / "render_report.md").write_text(
        "\n".join(
            [
                "# Render Report",
                "",
                f"- Image count: {len(images)}",
                f"- Audio duration seconds: {audio_duration}",
                f"- Average image duration seconds: {base_duration}",
                "- Motion rule: horizontal pan only, alternating left/right, no zoom animation",
                f"- Timeline: {timeline_json_path}",
                f"- FFconcat: {ffconcat_path}",
                f"- Output: {output_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
