import argparse
import json
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://veononstop.org/api/v1"
ENV_PATH = Path(r"C:\Users\MIKE\Documents\Codex\YT\.env")
DEFAULT_WORKDIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\veononstop_text_run")
TIMEOUT_SNIPPETS = ("Read timed out", "HTTPSConnectionPool")
COOKIE_SLOT_SNIPPETS = ("All cookie slots full", "cookie slots full")


def load_env_value(key: str) -> str:
    if key in os.environ and os.environ[key].strip():
        return os.environ[key].strip()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} not found in .env")


def load_prompt_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    return [block.strip() for block in text.split("\n\n") if block.strip()]


def load_requested_durations(path: Path | None) -> list[str]:
    if not path:
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("requested durations json must contain a JSON array")
    normalized: list[str] = []
    for value in data:
        if value in (None, "", 8, "8", "8s"):
            normalized.append("")
            continue
        if value in (4, "4", "4s"):
            normalized.append("4s")
            continue
        if value in (6, "6", "6s"):
            normalized.append("6s")
            continue
        raise ValueError(f"Unsupported duration preset: {value!r}")
    return normalized


def is_read_timeout(exc: Exception) -> bool:
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    return any(snippet in str(exc) for snippet in TIMEOUT_SNIPPETS)


def is_cookie_slots_full_error(exc: Exception) -> bool:
    return any(snippet in str(exc) for snippet in COOKIE_SLOT_SNIPPETS)


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
            if is_read_timeout(exc) or isinstance(exc, requests.exceptions.ConnectionError):
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


def create_task(
    session: requests.Session,
    api_key: str,
    prompt: str,
    aspect_ratio: str,
    duration: str,
    count: int,
) -> dict[str, Any]:
    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "count": count,
    }
    if duration:
        payload["duration"] = duration
    response = request_with_retries(
        session,
        "POST",
        f"{BASE_URL}/video/text-to-video",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        json_body=payload,
        timeout=(30.0, 300.0),
        attempts=4,
        retry_sleep=8.0,
    )
    return response.json()


def get_status(session: requests.Session, api_key: str, task_id: str) -> dict[str, Any]:
    response = request_with_retries(
        session,
        "GET",
        f"{BASE_URL}/video/status/{task_id}",
        headers={"X-API-Key": api_key},
        timeout=(30.0, 300.0),
        attempts=5,
        retry_sleep=10.0,
    )
    return response.json()


def cancel_all_tasks(session: requests.Session, api_key: str) -> dict[str, Any]:
    response = request_with_retries(
        session,
        "POST",
        f"{BASE_URL}/video/cancel-all",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        json_body={},
        timeout=(30.0, 180.0),
        attempts=4,
        retry_sleep=8.0,
    )
    return response.json()


def download_video(session: requests.Session, api_key: str, task_id: str, target_path: Path) -> None:
    response = request_with_retries(
        session,
        "GET",
        f"{BASE_URL}/video/download/{task_id}",
        headers={"X-API-Key": api_key},
        timeout=(30.0, 600.0),
        attempts=5,
        retry_sleep=10.0,
        stream=True,
    )
    with target_path.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                fh.write(chunk)


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def derive_duration(duration_seconds: float) -> str:
    if duration_seconds <= 4.25:
        return "4s"
    if duration_seconds <= 6.25:
        return "6s"
    return ""


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts-file", required=True)
    parser.add_argument("--durations-json")
    parser.add_argument("--requested-durations-json")
    parser.add_argument("--workdir", default=str(DEFAULT_WORKDIR))
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--max-polls", type=int, default=180)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--task-retries", type=int, default=1)
    parser.add_argument("--retry-delay-seconds", type=float, default=20.0)
    parser.add_argument("--stop-after-consecutive-failures", type=int, default=0)
    parser.add_argument("--cookie-retry-delay-seconds", type=float, default=30.0)
    parser.add_argument("--cookie-reset-cooldown-seconds", type=float, default=45.0)
    parser.add_argument("--disable-auto-cookie-reset", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    prompts = load_prompt_blocks(Path(args.prompts_file))
    durations = json.loads(Path(args.durations_json).read_text(encoding="utf-8")) if args.durations_json else []
    requested_durations = load_requested_durations(Path(args.requested_durations_json)) if args.requested_durations_json else []
    api_key = load_env_value("VEO_NONSTOP_API_KEY")
    end_index = args.end if args.end > 0 else len(prompts)
    selected_indices = range(args.start, end_index + 1)

    workdir = Path(args.workdir)
    videos_dir = workdir / "videos"
    meta_dir = workdir / "meta"
    videos_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    failed_path = workdir / "failed.jsonl"
    success_path = workdir / "success.jsonl"
    manifest_path = workdir / "run_manifest.json"
    recovery_path = workdir / "recovery.jsonl"
    stop_reason_path = workdir / "stop_reason.json"
    if stop_reason_path.exists():
        stop_reason_path.unlink()

    manifest = []
    for prompt_index in selected_indices:
        prompt = prompts[prompt_index - 1]
        duration_seconds = float(durations[prompt_index - 1]) if prompt_index - 1 < len(durations) else 4.0
        explicit_duration = requested_durations[prompt_index - 1] if prompt_index - 1 < len(requested_durations) else None
        output_file = videos_dir / f"{prompt_index:03d}.mp4"
        manifest.append(
            {
                "source_prompt_index": prompt_index,
                "prompt": prompt,
                "duration_seconds": duration_seconds,
                "requested_duration": explicit_duration if explicit_duration is not None else derive_duration(duration_seconds),
                "output": str(output_file),
                "attempt": 0,
            }
        )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    session = requests.Session()
    run_summary = {"done": 0, "skipped": 0, "failed": 0}
    consecutive_terminal_failures = 0
    consecutive_error_events = 0
    submit_cooldown_until = 0.0

    pending = deque()
    for item in manifest:
        target_path = Path(item["output"])
        if target_path.exists() and target_path.stat().st_size > 0:
            run_summary["skipped"] += 1
            print(f"skip {item['source_prompt_index']:03d}")
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
            args.aspect_ratio,
            str(item["requested_duration"]),
            args.count,
        )
        if not create_result.get("success"):
            raise RuntimeError(json.dumps(create_result, ensure_ascii=False))
        task_id = create_result["data"]["task_id"]
        task_meta = {
            "source_prompt_index": item["source_prompt_index"],
            "attempt": item["attempt"],
            "task_id": task_id,
            "initial_status": create_result["data"].get("status"),
            "output": item["output"],
            "prompt": item["prompt"],
            "requested_duration": item["requested_duration"],
        }
        (meta_dir / f"{item['source_prompt_index']:03d}.submit.json").write_text(
            json.dumps(task_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        active.append({**item, "task_id": task_id, "poll_count": 0, "next_retry_at": 0.0})
        print(f"submitted {item['source_prompt_index']:03d} attempt={item['attempt']} task={task_id}")

    def auto_reset_cookie_capacity(item: dict[str, Any], stage: str) -> bool:
        nonlocal consecutive_terminal_failures, consecutive_error_events, submit_cooldown_until, active
        if args.disable_auto_cookie_reset:
            return False
        if args.stop_after_consecutive_failures <= 0:
            return False
        if consecutive_error_events < args.stop_after_consecutive_failures:
            return False

        active_items = list(active)
        try:
            cancel_result = cancel_all_tasks(session, api_key)
        except Exception as exc:
            append_jsonl(
                recovery_path,
                {
                    "kind": "cookie_capacity_reset_failed",
                    "stage": stage,
                    "trigger_prompt_index": item["source_prompt_index"],
                    "active_prompt_indices": [entry["source_prompt_index"] for entry in active_items],
                    "error": str(exc),
                },
            )
            return False

        reset_event = {
            "kind": "cookie_capacity_reset",
            "stage": stage,
            "trigger_prompt_index": item["source_prompt_index"],
            "active_prompt_indices": [entry["source_prompt_index"] for entry in active_items],
            "cancel_result": cancel_result,
        }
        append_jsonl(recovery_path, reset_event)

        requeue_items: list[dict[str, Any]] = []
        for entry in active_items:
            clean_entry = {k: v for k, v in entry.items() if k not in {"task_id", "poll_count", "next_retry_at"}}
            clean_entry["attempt"] = max(0, int(clean_entry.get("attempt", 0)) - 1)
            if not output_exists(clean_entry):
                requeue_items.append(clean_entry)

        requeue_items.sort(key=lambda row: int(row["source_prompt_index"]))
        for clean_entry in reversed(requeue_items):
            pending.appendleft(clean_entry)

        active = []
        consecutive_terminal_failures = 0
        consecutive_error_events = 0
        submit_cooldown_until = max(submit_cooldown_until, time.time() + args.cookie_reset_cooldown_seconds)
        print(
            f"auto-reset cookie capacity after {stage} errors; "
            f"cancelled remote queue and requeued prompts from {requeue_items[0]['source_prompt_index']:03d}"
            if requeue_items
            else f"auto-reset cookie capacity after {stage} errors; cancelled remote queue"
        )
        return True

    def should_stop_on_errors(item: dict[str, Any], stage: str) -> bool:
        if auto_reset_cookie_capacity(item, stage):
            return False
        if args.stop_after_consecutive_failures > 0 and consecutive_error_events >= args.stop_after_consecutive_failures:
            stop_reason = {
                "reason": "consecutive_error_events_limit",
                "limit": args.stop_after_consecutive_failures,
                "current": consecutive_error_events,
                "last_failed_prompt_index": item["source_prompt_index"],
                "stage": stage,
            }
            stop_reason_path.write_text(json.dumps(stop_reason, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(stop_reason, ensure_ascii=False))
            return True
        return False

    def handle_failure(item: dict[str, Any], task_id: str | None, exc: Exception, stage: str) -> bool:
        nonlocal consecutive_terminal_failures, consecutive_error_events, submit_cooldown_until
        consecutive_error_events += 1
        if is_cookie_slots_full_error(exc):
            failure = {
                "source_prompt_index": item["source_prompt_index"],
                "attempt": item.get("attempt", 0),
                "stage": stage,
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
            print(f"cookie-capacity backoff for {item['source_prompt_index']:03d}; retry in {args.cookie_retry_delay_seconds:.0f}s")
            return True

        can_retry = int(item.get("attempt", 0)) <= args.task_retries
        failure = {
            "source_prompt_index": item["source_prompt_index"],
            "attempt": item.get("attempt", 0),
            "stage": stage,
            "output": item["output"],
            "task_id": task_id,
            "error": str(exc),
            "will_retry": can_retry,
        }
        append_jsonl(failed_path, failure)
        if can_retry:
            print(
                f"requeue {item['source_prompt_index']:03d} after {stage} failure "
                f"(attempt {item.get('attempt', 0)} of {args.task_retries + 1}): {exc}"
            )
            pending.append(item)
            if args.retry_delay_seconds > 0:
                time.sleep(args.retry_delay_seconds)
            return True

        run_summary["failed"] += 1
        consecutive_terminal_failures += 1
        print(f"failed {item['source_prompt_index']:03d}: {exc}")
        return False

    def mark_active_cookie_backoff(item: dict[str, Any], task_id: str, exc: Exception, stage: str) -> None:
        nonlocal consecutive_error_events, submit_cooldown_until
        consecutive_error_events += 1
        failure = {
            "source_prompt_index": item["source_prompt_index"],
            "attempt": item.get("attempt", 0),
            "stage": stage,
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
            f"cookie-capacity backoff for active prompt {item['source_prompt_index']:03d}; "
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
                print(f"skip {item['source_prompt_index']:03d} (appeared during run)")
                continue
            try:
                submit_item(item)
            except Exception as exc:
                retried = handle_failure(item, None, exc, "submit")
                if args.stop_after_consecutive_failures > 0 and consecutive_terminal_failures > args.stop_after_consecutive_failures:
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
                        print(f"poll timeout {item['source_prompt_index']:03d} task={task_id}; reconnect and continue waiting")
                        next_active.append(item)
                        continue
                    raise

                if not status.get("success"):
                    raise RuntimeError(json.dumps(status, ensure_ascii=False))

                item["poll_count"] += 1
                state = status["data"]["status"]
                print(f"prompt {item['source_prompt_index']:03d} poll {item['poll_count']}: {state}")

                if state == "completed":
                    download_video(session, api_key, task_id, target_path)
                    done_record = {
                        "source_prompt_index": item["source_prompt_index"],
                        "attempt": item.get("attempt", 0),
                        "task_id": task_id,
                        "output": str(target_path),
                        "status": status["data"]["status"],
                        "videos": status["data"].get("videos", []),
                        "requested_duration": item["requested_duration"],
                    }
                    (meta_dir / f"{item['source_prompt_index']:03d}.done.json").write_text(
                        json.dumps(done_record, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    append_jsonl(success_path, done_record)
                    run_summary["done"] += 1
                    consecutive_terminal_failures = 0
                    consecutive_error_events = 0
                    print(f"done {item['source_prompt_index']:03d}")
                    continue

                if state == "failed":
                    raise RuntimeError(status["data"].get("error", "task failed"))
                if item["poll_count"] >= args.max_polls:
                    raise TimeoutError(f"Polling timed out for prompt {item['source_prompt_index']:03d}, task={task_id}")

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
                if args.stop_after_consecutive_failures > 0 and consecutive_terminal_failures > args.stop_after_consecutive_failures:
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

    (workdir / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
