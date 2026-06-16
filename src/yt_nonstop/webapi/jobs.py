from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.models import JobRecord


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_file(runtime_dir: Path) -> Path:
    return runtime_dir / "jobs.json"


@dataclass(slots=True)
class JobStartResult:
    accepted: bool
    job: JobRecord
    reason: str | None = None


class JobStore:
    def __init__(self, config: WebConfig) -> None:
        self.config = config
        self.config.ensure_runtime_dirs()
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = self._load_jobs()
        self._threads: dict[str, threading.Thread] = {}

    def _load_jobs(self) -> dict[str, JobRecord]:
        path = _job_file(self.config.runtime_dir)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["job_id"]: JobRecord(**item) for item in payload}

    def _save_jobs(self) -> None:
        path = _job_file(self.config.runtime_dir)
        payload = [job.model_dump() for job in sorted(self._jobs.values(), key=lambda item: item.started_at or "", reverse=True)]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_jobs(self) -> list[JobRecord]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.started_at or "", reverse=True)

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def active_job_for_project(self, project_id: str) -> JobRecord | None:
        for job in self._jobs.values():
            if job.project_id == project_id and job.status in {"queued", "running"} and not job.read_only:
                return job
        return None

    def read_logs(self, job_id: str, *, tail: int = 200) -> list[str]:
        job = self.get_job(job_id)
        path = Path(job.log_path)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-tail:]

    def start_job(self, *, project_id: str, command: list[str], read_only: bool = False) -> JobStartResult:
        with self._lock:
            active = self.active_job_for_project(project_id)
            log_path = self.config.runtime_dir / "logs" / f"{uuid.uuid4().hex}.log"
            if active and not read_only:
                rejected = JobRecord(
                    job_id=uuid.uuid4().hex,
                    project_id=project_id,
                    command=command,
                    status="rejected",
                    started_at=_iso_now(),
                    finished_at=_iso_now(),
                    exit_code=None,
                    log_path=str(log_path),
                    read_only=read_only,
                )
                self._jobs[rejected.job_id] = rejected
                self._save_jobs()
                return JobStartResult(accepted=False, job=rejected, reason=f"project already has active job {active.job_id}")

            job = JobRecord(
                job_id=uuid.uuid4().hex,
                project_id=project_id,
                command=command,
                status="queued",
                started_at=_iso_now(),
                finished_at=None,
                exit_code=None,
                log_path=str(log_path),
                read_only=read_only,
            )
            self._jobs[job.job_id] = job
            self._save_jobs()
            thread = threading.Thread(target=self._run_job, args=(job.job_id,), daemon=True)
            self._threads[job.job_id] = thread
            thread.start()
            return JobStartResult(accepted=True, job=job)

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            self._save_jobs()
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
            current = self._jobs[job_id]
            current.exit_code = exit_code
            current.finished_at = _iso_now()
            current.status = "completed" if exit_code == 0 else "failed"
            self._save_jobs()


def build_cli_command(
    *,
    project_json_path: str,
    action: str,
    from_stage: str | None = None,
    to_stage: str | None = None,
    profile: str | None = None,
    limit_frames: int = 0,
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
