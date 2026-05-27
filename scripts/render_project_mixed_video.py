import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


WIDTH = 1920
HEIGHT = 1080
FPS = 30


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def make_image_clip(source: Path, target: Path, duration: float) -> None:
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={FPS},format=yuv420p"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
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
        f"fps={FPS},tpad=stop_mode=clone:stop_duration=10,format=yuv420p"
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
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--output-name", default="")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_json(project_json)
    project_root = Path(project["meta"]["project_root"])
    mixed_manifest_path = Path(project["render"]["mixed_manifest_path"])
    audio_path = Path(project["inputs"]["audio_path"])
    mixed_manifest = load_json(mixed_manifest_path)

    output_dir = project_root / "exports"
    clips_dir = output_dir / "mixed_clips"
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    output_name = args.output_name or f"{project['project_id']}_mixed.mp4"
    output_video = output_dir / output_name
    ffconcat_path = output_dir / "mixed_timeline.ffconcat"
    timeline_snapshot_path = output_dir / "mixed_manifest_snapshot.json"
    render_report_path = project_root / "logs" / "mixed_render_report.md"

    clip_paths: list[Path] = []
    for item in mixed_manifest:
        shot_index = int(item["shot_index"])
        duration = float(item["duration"])
        source = Path(item["chosen_asset_path"])
        clip_path = clips_dir / f"{shot_index:03d}.mp4"
        if item["chosen_asset_type"] == "video":
            make_video_clip(source, clip_path, duration)
        else:
            make_image_clip(source, clip_path, duration)
        clip_paths.append(clip_path)

    write_ffconcat(clip_paths, ffconcat_path)
    timeline_snapshot_path.write_text(json.dumps(mixed_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

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
            str(output_video),
        ]
    )

    summary = {
        "output": str(output_video),
        "mixed_manifest_path": str(mixed_manifest_path),
        "ffconcat_path": str(ffconcat_path),
        "video_shots": sum(1 for item in mixed_manifest if item["chosen_asset_type"] == "video"),
        "image_shots": sum(1 for item in mixed_manifest if item["chosen_asset_type"] == "image"),
    }
    render_report_path.write_text(
        "\n".join(
            [
                "# Mixed Render Report",
                "",
                f"Output: {output_video}",
                f"Mixed manifest: {mixed_manifest_path}",
                f"Video shots: {summary['video_shots']}",
                f"Image shots: {summary['image_shots']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    project["render"]["status"] = "completed"
    project["render"]["render_strategy"] = "mixed_cut"
    project["render"]["final_video_path"] = str(output_video)
    project["render"]["ffconcat_path"] = str(ffconcat_path)
    project["logs"]["render_report_path"] = str(render_report_path)
    project["current_stage"] = "publishing_drafts"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
