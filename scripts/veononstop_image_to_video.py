import argparse
import base64
import json
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://veononstop.org/api/v1"
ENV_PATH = Path(r"C:\Users\MIKE\Documents\Codex\YT\.env")
DEFAULT_TIMELINE = Path(r"C:\Users\MIKE\Documents\Codex\YT\edit\timeline.json")
DEFAULT_WORKDIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\veononstop_run")

DEFAULT_MOTION_SUFFIX = (
    "Animate this exact still image into realistic cinematic motion. "
    "Preserve the same subject identity, clothing, environment, lighting, and composition. "
    "Natural movement only, no camera zoom, no reframing, no morphing, no text, no extra objects."
)

TIMEOUT_SNIPPETS = (
    "Read timed out",
    "HTTPSConnectionPool",
)

COOKIE_SLOT_SNIPPETS = (
    "All cookie slots full",
    "cookie slots full",
)


def load_env_value(key: str) -> str:
    if key in os.environ and os.environ[key].strip():
        return os.environ[key].strip()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} not found in .env")


def is_read_timeout(exc: Exception) -> bool:
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    message = str(exc)
    return any(snippet in message for snippet in TIMEOUT_SNIPPETS)


def is_cookie_slots_full_error(exc: Exception) -> bool:
    message = str(exc)
    return any(snippet in message for snippet in COOKIE_SLOT_SNIPPETS)


def request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: tuple[float, float] = (30.0, 300.0),
    attempts: int = 5,
    retry_sleep: float = 5.0,
    stream: bool = False,
):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=timeout,
                stream=stream,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            should_retry = False
            if is_read_timeout(exc):
                should_retry = True
            elif isinstance(exc, requests.exceptions.ConnectionError):
                should_retry = True
            elif isinstance(exc, requests.exceptions.HTTPError):
                status = getattr(exc.response, "status_code", None)
                if status in {408, 425, 429, 500, 502, 503, 504}:
                    should_retry = True

            if not should_retry or attempt == attempts:
                break

            sleep_for = retry_sleep * attempt
            print(f"retry {method} {url} after error: {exc} | sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)

    assert last_error is not None
    raise last_error


def strip_reference_prefix(prompt: str) -> str:
    prompt = prompt.strip()
    prompt = re.sub(r"^Use reference images:\s+[A-Za-z0-9_,\s-]+\.\s*", "", prompt)
    prompt = re.sub(r"^Use reference image:\s+[A-Za-z0-9_\-]+\.\s*", "", prompt)
    prompt = re.sub(r"^No character reference\.\s*", "", prompt)
    return prompt.strip()


def image_to_base64(image_path: Path) -> tuple[str, str]:
    suffix = image_path.suffix.lower()
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return encoded, mime_type


def load_timeline(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("timeline.json must contain a JSON array")
    return data


def build_motion_prompt(source_prompt: str, motion_suffix: str) -> str:
    cleaned = strip_reference_prefix(source_prompt)
    if not cleaned:
        return motion_suffix
    if cleaned.endswith("."):
        return f"{cleaned} {motion_suffix}"
    return f"{cleaned}. {motion_suffix}"


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def create_task(
    session: requests.Session,
    api_key: str,
    prompt: str,
    image_path: Path,
    aspect_ratio: str,
    duration: str,
    count: int,
) -> dict[str, Any]:
    image_base64, mime_type = image_to_base64(image_path)
    payload = {
        "prompt": prompt,
        "image_base64": image_base64,
        "mime_type": mime_type,
        "aspect_ratio": aspect_ratio,
        "count": count,
    }
    if duration:
        payload["duration"] = duration
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    response = request_with_retries(
        session,
        "POST",
        f"{BASE_URL}/video/image-to-video",
        headers=headers,
        json_body=payload,
        timeout=(30.0, 300.0),
        attempts=4,
        retry_sleep=8.0,
    )
    return response.json()


def get_account_info(session: requests.Session, api_key: str) -> dict[str, Any]:
    headers = {"X-API-Key": api_key}
    response = request_with_retries(
        session,
        "GET",
        f"{BASE_URL}/account/info",
        headers=headers,
        timeout=(30.0, 120.0),
        attempts=4,
        retry_sleep=5.0,
    )
    return response.json()


def get_account_usage(session: requests.Session, api_key: str) -> dict[str, Any]:
    headers = {"X-API-Key": api_key}
    response = request_with_retries(
        session,
        "GET",
        f"{BASE_URL}/account/usage",
        headers=headers,
        timeout=(30.0, 120.0),
        attempts=4,
        retry_sleep=5.0,
    )
    return response.json()


def get_status(
    session: requests.Session,
    api_key: str,
    task_id: str,
) -> dict[str, Any]:
    headers = {"X-API-Key": api_key}
    response = request_with_retries(
        session,
        "GET",
        f"{BASE_URL}/video/status/{task_id}",
        headers=headers,
        timeout=(30.0, 300.0),
        attempts=5,
        retry_sleep=10.0,
    )
    return response.json()


def download_video(
    session: requests.Session,
    api_key: str,
    task_id: str,
    target_path: Path,
) -> None:
    headers = {"X-API-Key": api_key}
    response = request_with_retries(
        session,
        "GET",
        f"{BASE_URL}/video/download/{task_id}",
        headers=headers,
        timeout=(30.0, 600.0),
        attempts=5,
        retry_sleep=10.0,
        stream=True,
    )
    with target_path.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                fh.write(chunk)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--timeline", default=str(DEFAULT_TIMELINE))
    parser.add_argument("--workdir", default=str(DEFAULT_WORKDIR))
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--duration", default="")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--task-retries", type=int, default=1)
    parser.add_argument("--retry-delay-seconds", type=float, default=20.0)
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=0)
    parser.add_argument("--cookie-retry-delay-seconds", type=float, default=30.0)
    parser.add_argument("--motion-suffix", default=DEFAULT_MOTION_SUFFIX)
    parser.add_argument("--check-account", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    api_key = load_env_value("VEO_NONSTOP_API_KEY")
    timeline = load_timeline(Path(args.timeline))
    end_index = args.end if args.end > 0 else len(timeline)
    shots = [shot for shot in timeline if args.start <= int(shot["shot_index"]) <= end_index]

    workdir = Path(args.workdir)
    videos_dir = workdir / "videos"
    meta_dir = workdir / "meta"
    videos_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    failed_path = workdir / "failed.jsonl"
    success_path = workdir / "success.jsonl"
    manifest_path = workdir / "run_manifest.json"

    manifest = []
    for shot in shots:
        shot_index = int(shot["shot_index"])
        image_path = Path(shot["image"])
        output_file = videos_dir / f"{shot_index:03d}.mp4"
        manifest.append(
            {
                "shot_index": shot_index,
                "image": str(image_path),
                "output": str(output_file),
                "prompt": build_motion_prompt(str(shot.get("prompt", "")), args.motion_suffix),
                "source_prompt": str(shot.get("prompt", "")),
                "source_kind": shot.get("source_kind"),
                "duration": shot.get("duration"),
                "attempt": 0,
            }
        )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    session = requests.Session()
    run_summary = {"done": 0, "skipped": 0, "failed": 0}
    consecutive_terminal_failures = 0
    consecutive_error_events = 0
    submit_cooldown_until = 0.0
    if args.check_account:
        try:
            info = get_account_info(session, api_key)
            usage = get_account_usage(session, api_key)
            (workdir / "account_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            (workdir / "account_usage.json").write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"account check failed: {exc}")

    pending = deque()
    for item in manifest:
        target_path = Path(item["output"])
        if target_path.exists() and target_path.stat().st_size > 0:
            run_summary["skipped"] += 1
            print(f"skip {item['shot_index']:03d}")
            continue
        pending.append(item)

    active: list[dict[str, Any]] = []
    stop_requested = False

    def output_exists(item: dict[str, Any]) -> bool:
        target_path = Path(item["output"])
        return target_path.exists() and target_path.stat().st_size > 0

    def submit_item(item: dict[str, Any]) -> None:
        item["attempt"] = int(item.get("attempt", 0)) + 1
        create_result = create_task(
            session,
            api_key,
            item["prompt"],
            Path(item["image"]),
            args.aspect_ratio,
            args.duration,
            args.count,
        )
        if not create_result.get("success"):
            raise RuntimeError(json.dumps(create_result, ensure_ascii=False))

        task_id = create_result["data"]["task_id"]
        task_meta = {
            "shot_index": item["shot_index"],
            "attempt": item["attempt"],
            "task_id": task_id,
            "initial_status": create_result["data"].get("status"),
            "image": item["image"],
            "output": item["output"],
            "prompt": item["prompt"],
        }
        (meta_dir / f"{item['shot_index']:03d}.submit.json").write_text(
            json.dumps(task_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        active.append(
            {
                **item,
                "task_id": task_id,
                "poll_count": 0,
                "next_retry_at": 0.0,
            }
        )
        print(f"submitted {item['shot_index']:03d} attempt={item['attempt']} task={task_id}")

    def should_stop_on_errors(item: dict[str, Any], stage: str) -> bool:
        if args.stop_after_consecutive_failures > 0 and consecutive_error_events >= args.stop_after_consecutive_failures:
            stop_reason = {
                "reason": "consecutive_error_events_limit",
                "limit": args.stop_after_consecutive_failures,
                "current": consecutive_error_events,
                "last_failed_shot_index": item["shot_index"],
                "stage": stage,
            }
            (workdir / "stop_reason.json").write_text(
                json.dumps(stop_reason, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(json.dumps(stop_reason, ensure_ascii=False))
            return True
        return False

    def handle_failure(item: dict[str, Any], task_id: str | None, exc: Exception, stage: str) -> bool:
        nonlocal consecutive_terminal_failures, consecutive_error_events, submit_cooldown_until
        consecutive_error_events += 1
        if is_cookie_slots_full_error(exc):
            failure = {
                "shot_index": item["shot_index"],
                "attempt": item.get("attempt", 0),
                "stage": stage,
                "image": item["image"],
                "output": item["output"],
                "task_id": task_id,
                "error": str(exc),
                "will_retry": True,
                "retry_reason": "cookie_slots_full",
            }
            append_jsonl(failed_path, failure)
            item["attempt"] = max(0, int(item.get("attempt", 0)) - 1)
            pending.appendleft(item)
            submit_cooldown_until = max(submit_cooldown_until, time.time() + args.cookie_retry_delay_seconds)
            print(
                f"cookie-capacity backoff for {item['shot_index']:03d}; "
                f"retry in {args.cookie_retry_delay_seconds:.0f}s"
            )
            return True

        can_retry = int(item.get("attempt", 0)) <= args.task_retries
        failure = {
            "shot_index": item["shot_index"],
            "attempt": item.get("attempt", 0),
            "stage": stage,
            "image": item["image"],
            "output": item["output"],
            "task_id": task_id,
            "error": str(exc),
            "will_retry": can_retry,
        }
        append_jsonl(failed_path, failure)
        if can_retry:
            print(
                f"requeue {item['shot_index']:03d} after {stage} failure "
                f"(attempt {item.get('attempt', 0)} of {args.task_retries + 1}): {exc}"
            )
            pending.append(item)
            if args.retry_delay_seconds > 0:
                time.sleep(args.retry_delay_seconds)
            return True

        run_summary["failed"] += 1
        consecutive_terminal_failures += 1
        print(f"failed {item['shot_index']:03d}: {exc}")
        return False

    def mark_active_cookie_backoff(item: dict[str, Any], task_id: str, exc: Exception, stage: str) -> None:
        nonlocal consecutive_error_events, submit_cooldown_until
        consecutive_error_events += 1
        failure = {
            "shot_index": item["shot_index"],
            "attempt": item.get("attempt", 0),
            "stage": stage,
            "image": item["image"],
            "output": item["output"],
            "task_id": task_id,
            "error": str(exc),
            "will_retry": True,
            "retry_reason": "cookie_slots_full",
        }
        append_jsonl(failed_path, failure)
        item["next_retry_at"] = max(float(item.get("next_retry_at", 0.0)), time.time() + args.cookie_retry_delay_seconds)
        submit_cooldown_until = max(submit_cooldown_until, item["next_retry_at"])
        print(
            f"cookie-capacity backoff for active shot {item['shot_index']:03d}; "
            f"retry in {args.cookie_retry_delay_seconds:.0f}s"
        )

    while (pending or active) and not stop_requested:
        if time.time() < submit_cooldown_until:
            sleep_for = max(0.0, submit_cooldown_until - time.time())
            if sleep_for > 0:
                print(f"submit cooldown active, sleeping {sleep_for:.1f}s")
                time.sleep(sleep_for)

        while pending and len(active) < args.concurrency:
            item = pending.popleft()
            if output_exists(item):
                run_summary["skipped"] += 1
                print(f"skip {item['shot_index']:03d} (appeared during run)")
                continue
            try:
                submit_item(item)
            except Exception as exc:
                retried = handle_failure(item, None, exc, "submit")
                if (
                    args.stop_after_consecutive_failures > 0
                    and consecutive_terminal_failures > args.stop_after_consecutive_failures
                ):
                    stop_requested = True
                    break
                if should_stop_on_errors(item, "submit"):
                    stop_requested = True
                    break
                if args.stop_on_error and not retried:
                    stop_requested = True
                    break

        if stop_requested or not active:
            continue

        next_active: list[dict[str, Any]] = []
        for item in active:
            target_path = Path(item["output"])
            task_id = item["task_id"]
            now = time.time()
            if now < float(item.get("next_retry_at", 0.0)):
                next_active.append(item)
                continue
            try:
                try:
                    status = get_status(session, api_key, task_id)
                except Exception as exc:
                    if is_read_timeout(exc):
                        print(f"poll timeout {item['shot_index']:03d} task={task_id}; reconnect and continue waiting")
                        next_active.append(item)
                        continue
                    raise

                if not status.get("success"):
                    raise RuntimeError(json.dumps(status, ensure_ascii=False))

                item["poll_count"] += 1
                state = status["data"]["status"]
                print(f"shot {item['shot_index']:03d} poll {item['poll_count']}: {state}")

                if state == "completed":
                    download_video(session, api_key, task_id, target_path)
                    done_record = {
                        "shot_index": item["shot_index"],
                        "attempt": item.get("attempt", 0),
                        "task_id": task_id,
                        "output": str(target_path),
                        "status": status["data"]["status"],
                        "videos": status["data"].get("videos", []),
                    }
                    (meta_dir / f"{item['shot_index']:03d}.done.json").write_text(
                        json.dumps(done_record, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    append_jsonl(success_path, done_record)
                    run_summary["done"] += 1
                    consecutive_terminal_failures = 0
                    consecutive_error_events = 0
                    print(f"done {item['shot_index']:03d}")
                    continue

                if state == "failed":
                    raise RuntimeError(status["data"].get("error", "task failed"))

                if item["poll_count"] >= args.max_polls:
                    raise TimeoutError(f"Polling timed out for shot {item['shot_index']:03d}, task={task_id}")

                next_active.append(item)
            except Exception as exc:
                if is_cookie_slots_full_error(exc):
                    mark_active_cookie_backoff(item, task_id, exc, "poll_or_download")
                    if should_stop_on_errors(item, "poll_or_download"):
                        stop_requested = True
                        break
                    next_active.append(item)
                    continue
                retried = handle_failure(item, task_id, exc, "poll_or_download")
                if (
                    args.stop_after_consecutive_failures > 0
                    and consecutive_terminal_failures > args.stop_after_consecutive_failures
                ):
                    stop_requested = True
                    break
                if should_stop_on_errors(item, "poll_or_download"):
                    stop_requested = True
                    break
                if args.stop_on_error and not retried:
                    stop_requested = True
                    break

        active = next_active
        if active:
            time.sleep(args.poll_seconds)

    (workdir / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(run_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
