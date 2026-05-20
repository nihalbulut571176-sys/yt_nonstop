import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
TIMELINE_PATH = ROOT / "edit" / "timeline.json"
VIDEO_DIR = ROOT / "veononstop_run" / "videos"
AUDIO_PATH = ROOT / "assets" / "audio" / "message@elevenLabsVoicerBot.mp3"

WIDTH = 1672
HEIGHT = 942


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def load_timeline(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_manifest(shots: list[dict], start_shot: int, end_shot: int) -> list[dict]:
    manifest = []
    for shot in shots:
        shot_index = int(shot["shot_index"])
        if shot_index < start_shot or shot_index > end_shot:
            continue
        video_path = VIDEO_DIR / f"{shot_index:03d}.mp4"
        use_video = video_path.exists() and video_path.stat().st_size > 0
        manifest.append(
            {
                "shot_index": shot_index,
                "start": float(shot["start"]),
                "end": float(shot["end"]),
                "duration": float(shot["duration"]),
                "source_type": "video" if use_video else "image",
                "source_path": str(video_path if use_video else Path(shot["image"])),
                "generated_index": int(shot["generated_index"]),
            }
        )
    return manifest


def make_image_clip(source: Path, target: Path, duration: float) -> None:
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps=30,format=yuv420p"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(source),
            "-t",
            f"{duration:.6f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            str(target),
        ]
    )


def make_video_clip(source: Path, target: Path, duration: float) -> None:
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps=30,tpad=stop_mode=clone:stop_duration=10,format=yuv420p"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-t",
            f"{duration:.6f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            str(target),
        ]
    )


def write_ffconcat(clips: list[Path], path: Path) -> None:
    lines = ["ffconcat version 1.0"]
    for clip in clips:
        lines.append(f"file '{clip.as_posix()}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-shot", type=int, required=True)
    parser.add_argument("--end-shot", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-name", required=True)
    args = parser.parse_args()

    shots = load_timeline(TIMELINE_PATH)
    manifest = build_manifest(shots, args.start_shot, args.end_shot)
    if not manifest:
        raise RuntimeError("No shots selected")

    output_dir = Path(args.output_dir)
    clips_dir = output_dir / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "mixed_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    clip_paths: list[Path] = []
    for item in manifest:
        shot_index = int(item["shot_index"])
        clip_path = clips_dir / f"{shot_index:03d}.mp4"
        source = Path(item["source_path"])
        duration = float(item["duration"])
        if item["source_type"] == "video":
            make_video_clip(source, clip_path, duration)
        else:
            make_image_clip(source, clip_path, duration)
        clip_paths.append(clip_path)

    concat_path = output_dir / "timeline.ffconcat"
    write_ffconcat(clip_paths, concat_path)

    start_time = float(manifest[0]["start"])
    end_time = float(manifest[-1]["end"])
    audio_duration = end_time - start_time
    output_video = output_dir / args.output_name
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-ss",
            f"{start_time:.6f}",
            "-i",
            str(AUDIO_PATH),
            "-t",
            f"{audio_duration:.6f}",
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
            str(output_video),
        ]
    )

    summary = {
        "start_shot": args.start_shot,
        "end_shot": args.end_shot,
        "shots": len(manifest),
        "video_shots": sum(1 for item in manifest if item["source_type"] == "video"),
        "image_shots": sum(1 for item in manifest if item["source_type"] == "image"),
        "audio_start_time": start_time,
        "audio_end_time": end_time,
        "audio_duration": audio_duration,
        "output": str(output_video),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
