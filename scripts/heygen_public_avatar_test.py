import argparse
import json
import mimetypes
import os
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
AUDIO_PATH = ROOT / "assets" / "audio" / "message@elevenLabsVoicerBot.mp3"
WORKDIR = ROOT / "heygen_run"
TMP_DIR = WORKDIR / "tmp"
OUT_DIR = WORKDIR / "videos"
META_DIR = WORKDIR / "meta"

UPLOAD_URL = "https://upload.heygen.com/v1/asset"
CREATE_WEBM_URL = "https://api.heygen.com/v1/video.webm"
CREATE_MP4_URL = "https://api.heygen.com/v2/videos"
STATUS_URL = "https://api.heygen.com/v1/video_status.get"


def ensure_dirs() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def cut_audio(start: float, duration: float, output_path: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(AUDIO_PATH),
            "-vn",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )


def http_json(method: str, url: str, headers: dict[str, str], body: bytes | None = None) -> dict:
    req = Request(url, data=body, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        raise RuntimeError(
            json.dumps(
                {
                    "http_status": exc.code,
                    "url": url,
                    "response": parsed,
                },
                ensure_ascii=False,
                indent=2,
            )
        ) from exc


def upload_audio(api_key: str, path: Path) -> dict:
    mime_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
    body = path.read_bytes()
    return http_json(
        "POST",
        UPLOAD_URL,
        {
            "X-API-KEY": api_key,
            "Content-Type": mime_type,
        },
        body,
    )


def create_webm_video(
    api_key: str,
    avatar_pose_id: str,
    input_audio: str,
    width: int,
    height: int,
    avatar_style: str,
) -> dict:
    payload = {
        "avatar_pose_id": avatar_pose_id,
        "avatar_style": avatar_style,
        "input_audio": input_audio,
        "dimension": {
            "width": width,
            "height": height,
        },
    }
    return http_json(
        "POST",
        CREATE_WEBM_URL,
        {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        json.dumps(payload).encode("utf-8"),
    )


def create_mp4_video(
    api_key: str,
    avatar_id: str,
    audio_asset_id: str,
    resolution: str,
    aspect_ratio: str,
    title: str,
) -> dict:
    payload = {
        "avatar_id": avatar_id,
        "audio_asset_id": audio_asset_id,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "title": title,
        "remove_background": False,
    }
    return http_json(
        "POST",
        CREATE_MP4_URL,
        {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        json.dumps(payload).encode("utf-8"),
    )


def get_status(api_key: str, video_id: str) -> dict:
    qs = urlencode({"video_id": video_id})
    return http_json(
        "GET",
        f"{STATUS_URL}?{qs}",
        {
            "X-API-KEY": api_key,
        },
    )


def download_file(url: str, output_path: Path) -> None:
    req = Request(url, method="GET")
    with urlopen(req, timeout=300) as resp:
        output_path.write_bytes(resp.read())


def first_present(data: dict, *keys: str):
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def first_present_nested(data: dict, *paths: tuple[str, ...]):
    for path in paths:
        current = data
        found = True
        for key in path:
            if not isinstance(current, dict) or key not in current:
                found = False
                break
            current = current[key]
        if found and current not in (None, ""):
            return current
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--avatar-pose-id", required=True)
    parser.add_argument("--mode", choices=["webm", "mp4"], default="mp4")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--avatar-style", default="normal", choices=["normal", "closeUp"])
    parser.add_argument("--output-name", default="heygen_public_avatar_test.mp4")
    parser.add_argument("--resolution", choices=["720p", "1080p"], default="720p")
    parser.add_argument("--aspect-ratio", choices=["16:9", "9:16"], default="16:9")
    parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args()

    ensure_dirs()

    env = load_env(ROOT / ".env")
    api_key = env.get("HEYGEN_API_KEY") or os.environ.get("HEYGEN_API_KEY")
    if not api_key:
        raise RuntimeError("HEYGEN_API_KEY is not set")

    audio_clip = TMP_DIR / f"audio_{int(args.start * 1000)}_{int(args.duration * 1000)}.mp3"
    cut_audio(args.start, args.duration, audio_clip)

    upload_result = upload_audio(api_key, audio_clip)
    asset_id = first_present(upload_result, "id", "asset_id") or first_present_nested(
        upload_result,
        ("data", "id"),
        ("data", "asset_id"),
    )
    if not asset_id:
        raise RuntimeError(f"Upload asset_id missing: {upload_result}")
    (META_DIR / "last_upload.json").write_text(
        json.dumps(upload_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.mode == "webm":
        create_result = create_webm_video(
            api_key=api_key,
            avatar_pose_id=args.avatar_pose_id,
            input_audio=asset_id,
            width=args.width,
            height=args.height,
            avatar_style=args.avatar_style,
        )
    else:
        create_result = create_mp4_video(
            api_key=api_key,
            avatar_id=args.avatar_pose_id,
            audio_asset_id=asset_id,
            resolution=args.resolution,
            aspect_ratio=args.aspect_ratio,
            title=f"codex_test_{args.avatar_pose_id}_{int(args.start)}_{int(args.duration)}",
        )
    video_id = first_present(create_result, "video_id", "id") or first_present_nested(
        create_result,
        ("data", "video_id"),
        ("data", "id"),
    )
    if not video_id:
        raise RuntimeError(f"Create video_id missing: {create_result}")
    (META_DIR / "last_create.json").write_text(
        json.dumps(create_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    started = time.time()
    while True:
        status = get_status(api_key, video_id)
        (META_DIR / "last_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        status_value = str(
            first_present(status, "status", "state")
            or first_present_nested(status, ("data", "status"), ("data", "state"))
            or ""
        ).lower()
        if status_value == "completed":
            video_url = first_present(status, "video_url", "url") or first_present_nested(
                status,
                ("data", "video_url"),
                ("data", "url"),
                ("data", "video_url_with_watermark"),
            )
            if not video_url:
                raise RuntimeError(f"Completed without video_url: {status}")
            output_path = OUT_DIR / args.output_name
            download_file(video_url, output_path)
            print(
                json.dumps(
                    {
                        "status": "completed",
                        "video_id": video_id,
                        "output": str(output_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        if status_value == "failed":
            raise RuntimeError(json.dumps(status, ensure_ascii=False, indent=2))
        if time.time() - started > args.timeout_seconds:
            raise TimeoutError(f"Timed out waiting for video {video_id}")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
