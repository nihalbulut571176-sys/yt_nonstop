import argparse
import json
import math
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project


STATIC_MOTION_TYPES = {"static_hold"}
PUSH_MOTION_TYPES = {"slow_push_in", "subtle_push_in", "slight_push"}
PAN_MOTION_TYPES = {"slow_pan", "slow_pan_left", "slow_pan_right"}
PULL_MOTION_TYPES = {"slow_pull_out"}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(cmd: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=capture_output, text=True)


def ffprobe_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
    )
    data = json.loads(result.stdout or "{}")
    return float(data.get("format", {}).get("duration", 0) or 0)


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def load_edl(project: dict[str, Any]) -> list[dict[str, Any]]:
    edl_path = Path(project["render"].get("edit_decision_list_path", ""))
    if not edl_path.exists():
        return []
    payload = load_json(edl_path)
    rows = payload.get("edl", []) if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def runtime_time_range(project: dict[str, Any]) -> dict[str, Any]:
    time_range = project.get("runtime", {}).get("time_range", {})
    if not isinstance(time_range, dict) or not time_range.get("enabled") or time_range.get("audio_pretrimmed"):
        return {"enabled": False}
    start = max(0.0, float(time_range.get("start_sec", 0) or 0))
    end = float(time_range.get("end_sec", 0) or 0)
    if end <= start:
        return {"enabled": False}
    return {"enabled": True, "start_sec": start, "end_sec": end, "duration_sec": end - start}


def quote_filter_path(path: Path) -> str:
    return str(path)


def _zoom_for_intensity(motion_type: str, intensity: str) -> tuple[float, float]:
    intensity = str(intensity or "low").lower()
    if motion_type in STATIC_MOTION_TYPES:
        return 1.0, 1.0
    if motion_type in {"subtle_push_in", "slight_push"}:
        return 1.0, {"low": 1.025, "medium": 1.04, "high": 1.055}.get(intensity, 1.025)
    if motion_type in PULL_MOTION_TYPES:
        return {"low": 1.045, "medium": 1.065, "high": 1.085}.get(intensity, 1.045), 1.0
    if motion_type in PAN_MOTION_TYPES:
        return {"low": 1.035, "medium": 1.055, "high": 1.075}.get(intensity, 1.035), {"low": 1.035, "medium": 1.055, "high": 1.075}.get(intensity, 1.035)
    return 1.0, {"low": 1.045, "medium": 1.065, "high": 1.085}.get(intensity, 1.045)


def _anchor_xy(anchor: str) -> tuple[str, str]:
    anchor = str(anchor or "center").lower()
    x = "(iw-iw/zoom)/2"
    y = "(ih-ih/zoom)/2"
    if "left" in anchor:
        x = "0"
    elif "right" in anchor:
        x = "iw-iw/zoom"
    if "top" in anchor:
        y = "0"
    elif "bottom" in anchor:
        y = "ih-ih/zoom"
    return x, y


def motion_filter_for_row(row: dict[str, Any], index: int, *, width: int, height: int, fps: int) -> str:
    duration = max(0.001, float(row.get("duration", 0) or 0))
    frames = max(1, int(math.ceil(duration * fps)))
    motion_type = str(row.get("motion_type") or row.get("motion") or "slow_push_in").lower()
    intensity = str(row.get("motion_intensity") or "low").lower()
    anchor = str(row.get("crop_anchor") or "center").lower()

    base = f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    if motion_type in STATIC_MOTION_TYPES:
        return f"{base},fps={fps},trim=duration={duration:.6f},setpts=PTS-STARTPTS[v{index}]"

    start_zoom, end_zoom = _zoom_for_intensity(motion_type, intensity)
    if motion_type in PULL_MOTION_TYPES:
        zoom_expr = f"max({end_zoom:.5f},{start_zoom:.5f}-(on/{frames})*({start_zoom - end_zoom:.5f}))"
    elif motion_type in PAN_MOTION_TYPES:
        zoom_expr = f"{end_zoom:.5f}"
    else:
        zoom_expr = f"min({end_zoom:.5f},{start_zoom:.5f}+(on/{frames})*({end_zoom - start_zoom:.5f}))"

    if motion_type == "slow_pan_left":
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "(ih-ih/zoom)/2"
    elif motion_type in {"slow_pan", "slow_pan_right"}:
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        y_expr = "(ih-ih/zoom)/2"
    else:
        x_expr, y_expr = _anchor_xy(anchor)

    return (
        f"{base},zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height}:fps={fps},"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS[v{index}]"
    )


def build_motion_ffmpeg_command(
    *,
    edl: list[dict[str, Any]],
    audio_path: Path,
    final_video_path: Path,
    fps: int,
    width: int,
    height: int,
    preset: str,
    crf: str,
    audio_start_sec: float | None = None,
    audio_duration_sec: float | None = None,
) -> list[str]:
    if not edl:
        raise RuntimeError("Cannot build motion render command without edit_decision_list rows")

    cmd: list[str] = ["ffmpeg", "-y"]
    for row in edl:
        image_path = Path(str(row.get("image_path") or row.get("image") or ""))
        require_file(image_path, f"EDL image for {row.get('frame_id') or row.get('scene_id')}")
        duration = max(0.001, float(row.get("duration", 0) or 0))
        cmd.extend(["-loop", "1", "-t", f"{duration:.6f}", "-i", quote_filter_path(image_path)])
    audio_index = len(edl)
    if audio_start_sec is not None:
        cmd.extend(["-ss", f"{audio_start_sec:.6f}"])
    if audio_duration_sec is not None:
        cmd.extend(["-t", f"{audio_duration_sec:.6f}"])
    cmd.extend(["-i", str(audio_path)])

    filters = [motion_filter_for_row(row, index, width=width, height=height, fps=fps) for index, row in enumerate(edl)]
    concat_inputs = "".join(f"[v{index}]" for index in range(len(edl)))
    filters.append(f"{concat_inputs}concat=n={len(edl)}:v=1:a=0,format=yuv420p[v]")
    filter_complex = ";".join(filters)

    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            f"{audio_index}:a:0",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(final_video_path),
        ]
    )
    return cmd


def build_static_ffconcat_command(
    *,
    ffconcat_path: Path,
    audio_path: Path,
    final_video_path: Path,
    fps: int,
    preset: str,
    crf: str,
    audio_start_sec: float | None = None,
    audio_duration_sec: float | None = None,
) -> list[str]:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(ffconcat_path),
    ]
    if audio_start_sec is not None:
        cmd.extend(["-ss", f"{audio_start_sec:.6f}"])
    if audio_duration_sec is not None:
        cmd.extend(["-t", f"{audio_duration_sec:.6f}"])
    cmd.extend(
        [
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-filter:v",
        f"pad=ceil(iw/2)*2:ceil(ih/2)*2:color=black,fps={fps},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(final_video_path),
        ]
    )
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a project slideshow from edit_decision_list/ffconcat plus audio using Python + FFmpeg.")
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and write a render report without invoking ffmpeg.")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--crf", default="18")
    parser.add_argument("--disable-motion", action="store_true", help="Use the legacy static ffconcat render path.")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    ffconcat_path = Path(project["render"].get("ffconcat_path", ""))
    audio_path = Path(project["inputs"].get("audio_path") or project["transcription"].get("audio_path") or "")
    final_video_path = Path(project["render"].get("final_video_path") or (Path(project["meta"]["project_root"]) / "renders" / "final_video.mp4"))
    report_json_path = Path(project["render"].get("render_report_json_path") or (Path(project["meta"]["project_root"]) / "logs" / "render_report.json"))
    report_md_path = Path(project["logs"].get("render_report_path") or report_json_path.with_suffix(".md"))
    final_qa_report_path = Path(project["logs"].get("final_qa_report_path") or (Path(project["meta"]["project_root"]) / "logs" / "final_qa_report.md"))

    require_file(ffconcat_path, "render.ffconcat_path")
    require_file(audio_path, "inputs.audio_path")
    if shutil.which("ffmpeg") is None and not args.dry_run:
        raise RuntimeError("ffmpeg executable not found on PATH")
    if shutil.which("ffprobe") is None and not args.dry_run:
        raise RuntimeError("ffprobe executable not found on PATH")

    final_video_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    final_qa_report_path.parent.mkdir(parents=True, exist_ok=True)

    edl = load_edl(project)
    time_range = runtime_time_range(project)
    audio_start_sec = float(time_range["start_sec"]) if time_range.get("enabled") else None
    audio_duration_sec = float(time_range["duration_sec"]) if time_range.get("enabled") else None
    motion_enabled = bool(edl) and not args.disable_motion
    if motion_enabled:
        cmd = build_motion_ffmpeg_command(
            edl=edl,
            audio_path=audio_path,
            final_video_path=final_video_path,
            fps=args.fps,
            width=args.width,
            height=args.height,
            preset=args.preset,
            crf=str(args.crf),
            audio_start_sec=audio_start_sec,
            audio_duration_sec=audio_duration_sec,
        )
        render_mode = "motion_edl"
    else:
        cmd = build_static_ffconcat_command(
            ffconcat_path=ffconcat_path,
            audio_path=audio_path,
            final_video_path=final_video_path,
            fps=args.fps,
            preset=args.preset,
            crf=str(args.crf),
            audio_start_sec=audio_start_sec,
            audio_duration_sec=audio_duration_sec,
        )
        render_mode = "static_ffconcat"

    audio_duration = float(audio_duration_sec or 0.0) if time_range.get("enabled") else (0.0 if args.dry_run else ffprobe_duration(audio_path))
    if args.dry_run:
        status = "dry_run"
        output_bytes = 0
        final_duration = 0.0
    else:
        run(cmd)
        require_file(final_video_path, "final video")
        output_bytes = final_video_path.stat().st_size
        final_duration = ffprobe_duration(final_video_path)
        status = "success"

    motion_summary = {
        "enabled": motion_enabled,
        "render_mode": render_mode,
        "edl_rows": len(edl),
        "motion_types": sorted({str(row.get("motion_type") or row.get("motion") or "").strip() for row in edl if str(row.get("motion_type") or row.get("motion") or "").strip()}),
        "transition_styles": sorted({str(row.get("transition_style") or "").strip() for row in edl if str(row.get("transition_style") or "").strip()}),
        "width": args.width,
        "height": args.height,
        "fps": args.fps,
    }
    report = {
        "project_id": project.get("project_id"),
        "created_at": iso_now(),
        "status": status,
        "dry_run": args.dry_run,
        "render_mode": render_mode,
        "motion_summary": motion_summary,
        "ffmpeg_command": cmd,
        "ffmpeg_command_string": " ".join(shlex.quote(part) for part in cmd),
        "ffconcat_path": str(ffconcat_path),
        "audio_path": str(audio_path),
        "time_range": time_range,
        "final_video_path": str(final_video_path),
        "output_bytes": output_bytes,
        "audio_duration_seconds": round(audio_duration, 6),
        "final_video_duration_seconds": round(final_duration, 6),
        "duration_delta_seconds": round(abs(audio_duration - final_duration), 6) if audio_duration and final_duration else None,
        "ready_for_upload": status == "success" and output_bytes > 0,
    }
    save_json(report_json_path, report)
    report_md_path.write_text(
        "\n".join(
            [
                "# Render Report",
                "",
                f"- Status: {status}",
                f"- Dry run: {'true' if args.dry_run else 'false'}",
                f"- Render mode: {render_mode}",
                f"- Motion enabled: {'true' if motion_enabled else 'false'}",
                f"- Motion types: {', '.join(motion_summary['motion_types']) or 'none'}",
                f"- Final video: {final_video_path}",
                f"- Output bytes: {output_bytes}",
                f"- FFconcat: {ffconcat_path}",
                f"- Audio: {audio_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    final_qa_report_path.write_text(
        "\n".join(
            [
                "# Final QA Report",
                "",
                f"Render status: {status}",
                f"Render mode: {render_mode}",
                f"Motion enabled: {'true' if motion_enabled else 'false'}",
                f"Final output: {final_video_path}",
                f"Output bytes: {output_bytes}",
                f"Timeline source: {ffconcat_path}",
                f"Audio source: {audio_path}",
                f"Ready for upload: {'true' if report['ready_for_upload'] else 'false'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    project["render"]["render_report_json_path"] = str(report_json_path)
    project["logs"]["render_report_path"] = str(report_md_path)
    project["logs"]["final_qa_report_path"] = str(final_qa_report_path)
    project["render"]["final_video_path"] = str(final_video_path)
    project["render"]["motion_enabled"] = motion_enabled
    project["render"]["render_mode"] = render_mode
    project["render"]["status"] = "dry_run" if args.dry_run else "completed"
    project["current_stage"] = "production_report"
    save_project(project_json, project)
    print(report_json_path)


if __name__ == "__main__":
    main()
