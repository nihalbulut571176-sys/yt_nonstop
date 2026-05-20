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


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_timeline(path: Path) -> list[dict]:
    return load_json(path)


def load_overrides(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    overrides = load_json(path)
    return sorted(overrides, key=lambda item: float(item["start"]))


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


def build_manifest(
    shots: list[dict],
    start_shot: int,
    end_shot: int,
    overrides: list[dict],
) -> list[dict]:
    subset = [shot for shot in shots if start_shot <= int(shot["shot_index"]) <= end_shot]
    if not subset:
        return []

    override_index = 0
    manifest: list[dict] = []

    for shot in subset:
        shot_start = float(shot["start"])
        shot_end = float(shot["end"])
        shot_index = int(shot["shot_index"])

        while override_index < len(overrides) and float(overrides[override_index]["end"]) <= shot_start:
            override_index += 1

        current = overrides[override_index] if override_index < len(overrides) else None
        if current is not None:
            override_start = float(current["start"])
            override_end = float(current["end"])

            if shot_start < override_end and shot_end > override_start:
                if abs(shot_start - override_start) < 1e-6:
                    manifest.append(
                        {
                            "shot_index": shot_index,
                            "start": override_start,
                            "end": override_end,
                            "duration": override_end - override_start,
                            "source_type": "override_video",
                            "source_path": current["video"],
                            "label": current.get("label", f"override_{override_start:.3f}"),
                        }
                    )
                continue

        video_path = VIDEO_DIR / f"{shot_index:03d}.mp4"
        use_video = video_path.exists() and video_path.stat().st_size > 0
        manifest.append(
            {
                "shot_index": shot_index,
                "start": shot_start,
                "end": shot_end,
                "duration": float(shot["duration"]),
                "source_type": "video" if use_video else "image",
                "source_path": str(video_path if use_video else Path(shot["image"])),
                "generated_index": int(shot["generated_index"]),
            }
        )

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-shot", type=int, required=True)
    parser.add_argument("--end-shot", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--overrides-json")
    args = parser.parse_args()

    shots = load_timeline(TIMELINE_PATH)
    overrides = load_overrides(Path(args.overrides_json)) if args.overrides_json else []
    manifest = build_manifest(shots, args.start_shot, args.end_shot, overrides)
    if not manifest:
        raise RuntimeError("No shots selected")

    output_dir = Path(args.output_dir)
    clips_dir = output_dir / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "mixed_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    clip_paths: list[Path] = []
    for idx, item in enumerate(manifest, start=1):
        if item["source_type"] == "override_video":
            clip_name = f"override_{idx:03d}.mp4"
        else:
            clip_name = f"{int(item['shot_index']):03d}.mp4"
        clip_path = clips_dir / clip_name
        source = Path(item["source_path"])
        duration = float(item["duration"])
        if item["source_type"] in {"video", "override_video"}:
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
        "override_shots": sum(1 for item in manifest if item["source_type"] == "override_video"),
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
