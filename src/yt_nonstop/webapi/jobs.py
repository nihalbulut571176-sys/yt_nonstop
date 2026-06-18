from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from yt_nonstop.webapi.app_state import AppStateStore
from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.models import RunSummary


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _job_file(runtime_dir: Path) -> Path:
    return runtime_dir / "jobs.json"


def _append_stale_log(path: Path, run_id: str) -> None:
    if not str(path):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{_iso_now()}] Run {run_id} was marked failed after Studio restart; no worker thread was attached.\n")


@dataclass(slots=True)
class JobStartResult:
    accepted: bool
    job: RunSummary
    reason: str | None = None


class JobStore:
    def __init__(self, config: WebConfig, app_state: AppStateStore | None = None) -> None:
        self.config = config
        self.app_state = app_state
        self.config.ensure_runtime_dirs()
        self._lock = threading.RLock()
        self._jobs: dict[str, RunSummary] = self._load_jobs()
        self._threads: dict[str, threading.Thread] = {}

    def _load_jobs(self) -> dict[str, RunSummary]:
        path = _job_file(self.config.runtime_dir)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        jobs: dict[str, RunSummary] = {}
        changed = False
        for item in payload:
            normalized = dict(item)
            if "run_id" not in normalized and "job_id" in normalized:
                normalized["run_id"] = normalized.pop("job_id")
            if "action_type" not in normalized:
                normalized["action_type"] = _infer_action_type(normalized.get("command", []))
            if normalized.get("status") in {"queued", "running"}:
                normalized["status"] = "failed"
                normalized["finished_at"] = normalized.get("finished_at") or _iso_now()
                normalized["exit_code"] = normalized.get("exit_code") if normalized.get("exit_code") is not None else -1
                normalized["error_category"] = normalized.get("error_category") or "system_error"
                _append_stale_log(Path(str(normalized.get("log_path") or "")), normalized.get("run_id", "unknown"))
                changed = True
            job = RunSummary(**normalized)
            jobs[job.run_id] = job
            if changed and self.app_state and job.status == "failed":
                self.app_state.record_run(job, user_id=job.user_id, error_category=job.error_category)
                self.app_state.record_run_event(job.run_id, event_type="failed", message="Run was marked failed because the Studio server restarted before the worker started or finished.")
        if changed:
            path.write_text(json.dumps([job.model_dump() for job in jobs.values()], ensure_ascii=False, indent=2), encoding="utf-8")
        return jobs

    def _save_jobs(self) -> None:
        path = _job_file(self.config.runtime_dir)
        payload = [job.model_dump() for job in sorted(self._jobs.values(), key=lambda item: item.started_at or "", reverse=True)]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_jobs(self, *, project_id: str | None = None, limit: int | None = None) -> list[RunSummary]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda item: item.started_at or "", reverse=True)
            if project_id:
                items = [item for item in items if item.project_id == project_id]
            if limit is not None:
                items = items[:limit]
            return items

    def get_job(self, run_id: str) -> RunSummary:
        with self._lock:
            if run_id not in self._jobs:
                raise KeyError(run_id)
            return self._jobs[run_id]

    def active_job_for_project(self, project_id: str) -> RunSummary | None:
        with self._lock:
            for job in self._jobs.values():
                if job.project_id == project_id and job.status in {"queued", "running"} and not job.read_only:
                    return job
            return None

    def read_logs(self, run_id: str, *, tail: int = 200) -> list[str]:
        job = self.get_job(run_id)
        path = Path(job.log_path)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-tail:]

    def start_job(self, *, project_id: str, command: list[str], read_only: bool = False, user_id: int | None = None) -> JobStartResult:
        with self._lock:
            active = self.active_job_for_project(project_id)
            log_path = self.config.runtime_dir / "logs" / f"{uuid.uuid4().hex}.log"
            if active and not read_only:
                rejected = RunSummary(
                    run_id=uuid.uuid4().hex,
                    project_id=project_id,
                    action_type=_infer_action_type(command),
                    command=command,
                    status="rejected",
                    started_at=_iso_now(),
                    finished_at=_iso_now(),
                    exit_code=None,
                    log_path=str(log_path),
                    read_only=read_only,
                    user_id=user_id,
                    error_category="run_conflict_error",
                )
                self._jobs[rejected.run_id] = rejected
                self._save_jobs()
                if self.app_state:
                    self.app_state.record_run(rejected, user_id=user_id, error_category="run_conflict_error")
                    self.app_state.record_run_event(rejected.run_id, event_type="rejected", message=f"Project already has active run {active.run_id}.")
                return JobStartResult(accepted=False, job=rejected, reason=f"project already has active job {active.run_id}")

            job = RunSummary(
                run_id=uuid.uuid4().hex,
                project_id=project_id,
                action_type=_infer_action_type(command),
                command=command,
                status="queued",
                started_at=_iso_now(),
                finished_at=None,
                exit_code=None,
                log_path=str(log_path),
                read_only=read_only,
                user_id=user_id,
            )
            self._jobs[job.run_id] = job
            self._save_jobs()
            if self.app_state:
                self.app_state.record_run(job, user_id=user_id)
                self.app_state.record_run_event(job.run_id, event_type="queued", message="Run accepted and queued.")
            thread = threading.Thread(target=self._run_job, args=(job.run_id, user_id), daemon=True)
            self._threads[job.run_id] = thread
            thread.start()
            return JobStartResult(accepted=True, job=job)

    def _run_job(self, run_id: str, user_id: int | None = None) -> None:
        with self._lock:
            job = self._jobs[run_id]
            job.status = "running"
            self._save_jobs()
            if self.app_state:
                self.app_state.record_run(job, user_id=user_id)
                self.app_state.record_run_event(job.run_id, event_type="running", message="Run is now running.")
        log_path = Path(job.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            job.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self.config.repo_root),
        )
        with log_path.open("w", encoding="utf-8") as handle:
            handle.write(f"$ {' '.join(job.command)}\n")
            assert process.stdout is not None
            for line in process.stdout:
                handle.write(line)
                handle.flush()
        exit_code = process.wait()
        with self._lock:
            current = self._jobs[run_id]
            current.exit_code = exit_code
            current.finished_at = _iso_now()
            current.status = "completed" if exit_code == 0 else "failed"
            self._save_jobs()
            if self.app_state:
                error_category = None if exit_code == 0 else _classify_error_category(log_path)
                self.app_state.record_run(current, user_id=user_id, error_category=error_category)
                self.app_state.record_run_event(current.run_id, event_type=current.status, message=f"Run finished with exit code {exit_code}.")


def _infer_action_type(command: list[str]) -> str:
    if "validate" in command:
        return "validate"
    if "review" in command:
        return "review"
    if "render" in command:
        return "render"
    if "run" in command:
        return "run"
    return "command"


def _classify_error_category(log_path: Path) -> str:
    if not log_path.exists():
        return "system_error"
    content = log_path.read_text(encoding="utf-8", errors="replace").lower()
    if "validation" in content or "invalid" in content:
        return "validation_error"
    if "provider" in content or "fastgen" in content or "api" in content:
        return "provider_error"
    if "review" in content:
        return "project_state_error"
    if "render" in content or "ffmpeg" in content:
        return "project_state_error"
    if "file not found" in content or "not found" in content or "missing" in content:
        return "filesystem_error"
    return "system_error"


def build_cli_command(
    *,
    project_json_path: str,
    action: str,
    from_stage: str | None = None,
    to_stage: str | None = None,
    profile: str | None = None,
    limit_frames: int = 0,
    start_sec: float | None = None,
    end_sec: float | None = None,
    real_generation: bool = False,
    concurrency: int = 10,
    resume: bool = False,
    retry_failed_only: bool = False,
    render_dry_run: bool = False,
    dry_run: bool = False,
    stage: str | None = None,
) -> list[str]:
    command = [sys.executable, "-m", "yt_nonstop.cli", action, "--project-json", project_json_path]
    if action == "run":
        if from_stage:
            command.extend(["--from", from_stage])
        if to_stage:
            command.extend(["--to", to_stage])
        if profile:
            command.extend(["--profile", profile])
        if limit_frames:
            command.extend(["--limit-frames", str(limit_frames)])
        if start_sec is not None:
            command.extend(["--start-sec", f"{float(start_sec):.3f}"])
        if end_sec is not None:
            command.extend(["--end-sec", f"{float(end_sec):.3f}"])
        if real_generation:
            command.append("--real-generation")
        if concurrency:
            command.extend(["--concurrency", str(concurrency)])
        if resume:
            command.append("--resume")
        if retry_failed_only:
            command.append("--retry-failed-only")
        if render_dry_run:
            command.append("--render-dry-run")
        if dry_run:
            command.append("--dry-run")
    elif action == "validate":
        if stage:
            command.extend(["--stage", stage])
    elif action == "review":
        if dry_run:
            command.append("--dry-run")
    return command
