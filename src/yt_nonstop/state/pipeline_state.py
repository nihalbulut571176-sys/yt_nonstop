"""SQLite runtime state for resumable project generation.

The state file is intentionally project-local by default:

    <project_root>/pipeline_state.sqlite

It tracks frame-level generation state so a long video can resume after a
process crash without re-generating frames that already completed.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB_NAME = "pipeline_state.sqlite"
DEFAULT_STAGE = "generate_images"
TERMINAL_SUCCESS = "success"
RETRYABLE_STATUSES = {"pending", "running", "failed", "missing"}


@dataclass(frozen=True)
class FrameState:
    project_id: str
    frame_id: str
    visual_slot_id: str
    stage: str
    status: str
    attempt_count: int
    prompt_hash: str
    image_path: str
    provider_job_id: str
    error_message: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StageState:
    project_id: str
    stage_name: str
    status: str
    started_at: str
    finished_at: str
    input_hash: str
    output_hash: str
    error_message: str
    attempt_count: int
    updated_at: str


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_state_db_path(project_json: Path, project: dict[str, Any] | None = None, explicit_path: str | Path | None = None) -> Path:
    """Resolve the runtime state DB path for a project.

    Priority:
    1. explicit CLI/path argument;
    2. project["state"]["pipeline_state_path"];
    3. project meta root / pipeline_state.sqlite;
    4. project_json.parent / pipeline_state.sqlite.
    """

    if explicit_path:
        return Path(explicit_path).expanduser().resolve(strict=False)
    if project:
        configured = str(project.get("state", {}).get("pipeline_state_path") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve(strict=False)
        project_root = str(project.get("meta", {}).get("project_root") or "").strip()
        if project_root:
            return (Path(project_root) / DEFAULT_DB_NAME).resolve(strict=False)
    return (project_json.resolve().parent / DEFAULT_DB_NAME).resolve(strict=False)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def connect_stage_state(db_path: Path) -> sqlite3.Connection:
    return connect(db_path)


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS frame_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            frame_id TEXT NOT NULL,
            visual_slot_id TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            prompt_hash TEXT NOT NULL DEFAULT '',
            image_path TEXT NOT NULL DEFAULT '',
            provider_job_id TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, frame_id, visual_slot_id, stage)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frame_state_project_stage_status ON frame_state(project_id, stage, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frame_state_frame ON frame_state(project_id, frame_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stage_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            stage_name TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            input_hash TEXT NOT NULL DEFAULT '',
            output_hash TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, stage_name)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stage_state_project_status ON stage_state(project_id, status)")
    conn.commit()


def _row_to_state(row: sqlite3.Row | None) -> FrameState | None:
    if row is None:
        return None
    return FrameState(
        project_id=str(row["project_id"]),
        frame_id=str(row["frame_id"]),
        visual_slot_id=str(row["visual_slot_id"] or ""),
        stage=str(row["stage"]),
        status=str(row["status"]),
        attempt_count=int(row["attempt_count"] or 0),
        prompt_hash=str(row["prompt_hash"] or ""),
        image_path=str(row["image_path"] or ""),
        provider_job_id=str(row["provider_job_id"] or ""),
        error_message=str(row["error_message"] or ""),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def get_frame_state(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    frame_id: str,
    visual_slot_id: str = "",
    stage: str = DEFAULT_STAGE,
) -> FrameState | None:
    row = conn.execute(
        """
        SELECT * FROM frame_state
        WHERE project_id = ? AND frame_id = ? AND visual_slot_id = ? AND stage = ?
        """,
        (project_id, frame_id, visual_slot_id or "", stage),
    ).fetchone()
    return _row_to_state(row)


def get_frame_states_for_project(conn: sqlite3.Connection, *, project_id: str, stage: str | None = None) -> list[FrameState]:
    if stage:
        rows = conn.execute(
            "SELECT * FROM frame_state WHERE project_id = ? AND stage = ? ORDER BY frame_id, visual_slot_id",
            (project_id, stage),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM frame_state WHERE project_id = ? ORDER BY stage, frame_id, visual_slot_id",
            (project_id,),
        ).fetchall()
    return [_row_to_state(row) for row in rows if row is not None]  # type: ignore[list-item]


def _row_to_stage_state(row: sqlite3.Row | None) -> StageState | None:
    if row is None:
        return None
    return StageState(
        project_id=str(row["project_id"]),
        stage_name=str(row["stage_name"]),
        status=str(row["status"]),
        started_at=str(row["started_at"] or ""),
        finished_at=str(row["finished_at"] or ""),
        input_hash=str(row["input_hash"] or ""),
        output_hash=str(row["output_hash"] or ""),
        error_message=str(row["error_message"] or ""),
        attempt_count=int(row["attempt_count"] or 0),
        updated_at=str(row["updated_at"]),
    )


def get_stage_state(conn: sqlite3.Connection, *, project_id: str, stage_name: str) -> StageState | None:
    row = conn.execute(
        "SELECT * FROM stage_state WHERE project_id = ? AND stage_name = ?",
        (project_id, stage_name),
    ).fetchone()
    return _row_to_stage_state(row)


def get_stage_states_for_project(conn: sqlite3.Connection, *, project_id: str) -> list[StageState]:
    rows = conn.execute(
        "SELECT * FROM stage_state WHERE project_id = ? ORDER BY id, stage_name",
        (project_id,),
    ).fetchall()
    return [_row_to_stage_state(row) for row in rows if row is not None]  # type: ignore[list-item]


def upsert_stage_state(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    stage_name: str,
    status: str,
    started_at: str | None = None,
    finished_at: str | None = None,
    input_hash: str = "",
    output_hash: str = "",
    error_message: str = "",
    increment_attempt: bool = False,
) -> StageState:
    now = iso_now()
    existing = get_stage_state(conn, project_id=project_id, stage_name=stage_name)
    if existing is None:
        conn.execute(
            """
            INSERT INTO stage_state (
                project_id, stage_name, status, started_at, finished_at, input_hash,
                output_hash, error_message, attempt_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                stage_name,
                status,
                started_at or "",
                finished_at or "",
                input_hash,
                output_hash,
                error_message,
                1 if increment_attempt else 0,
                now,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE stage_state
            SET status = ?,
                started_at = CASE WHEN ? != '' THEN ? ELSE started_at END,
                finished_at = CASE WHEN ? != '' THEN ? ELSE finished_at END,
                input_hash = CASE WHEN ? != '' THEN ? ELSE input_hash END,
                output_hash = CASE WHEN ? != '' THEN ? ELSE output_hash END,
                error_message = CASE WHEN ? != '' THEN ? WHEN ? = '' AND ? = 'completed' THEN '' ELSE error_message END,
                attempt_count = attempt_count + ?,
                updated_at = ?
            WHERE project_id = ? AND stage_name = ?
            """,
            (
                status,
                started_at or "",
                started_at or "",
                finished_at or "",
                finished_at or "",
                input_hash,
                input_hash,
                output_hash,
                output_hash,
                error_message,
                error_message,
                error_message,
                status,
                1 if increment_attempt else 0,
                now,
                project_id,
                stage_name,
            ),
        )
    conn.commit()
    state = get_stage_state(conn, project_id=project_id, stage_name=stage_name)
    assert state is not None
    return state


def mark_stage_running(conn: sqlite3.Connection, *, project_id: str, stage_name: str, input_hash: str = "") -> StageState:
    now = iso_now()
    return upsert_stage_state(
        conn,
        project_id=project_id,
        stage_name=stage_name,
        status="running",
        started_at=now,
        finished_at="",
        input_hash=input_hash,
        output_hash="",
        error_message="",
        increment_attempt=True,
    )


def mark_stage_completed(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    stage_name: str,
    input_hash: str = "",
    output_hash: str = "",
) -> StageState:
    now = iso_now()
    return upsert_stage_state(
        conn,
        project_id=project_id,
        stage_name=stage_name,
        status="completed",
        finished_at=now,
        input_hash=input_hash,
        output_hash=output_hash,
        error_message="",
    )


def mark_stage_failed(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    stage_name: str,
    input_hash: str = "",
    output_hash: str = "",
    error_message: str = "",
) -> StageState:
    now = iso_now()
    return upsert_stage_state(
        conn,
        project_id=project_id,
        stage_name=stage_name,
        status="failed",
        finished_at=now,
        input_hash=input_hash,
        output_hash=output_hash,
        error_message=error_message,
    )


def state_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def resolve_stale_stages(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    ordered_stage_hashes: list[dict[str, Any]],
) -> list[str]:
    stale_stages: list[str] = []
    downstream_is_stale = False
    for item in ordered_stage_hashes:
        stage_name = str(item["stage_name"])
        current_input_hash = str(item.get("input_hash") or "")
        current_output_hash = str(item.get("output_hash") or "")
        output_exists = bool(item.get("output_exists", True))
        existing = get_stage_state(conn, project_id=project_id, stage_name=stage_name)
        if existing is None:
            downstream_is_stale = False
            continue
        reason = ""
        if downstream_is_stale and existing.status == "completed":
            reason = "Upstream stage changed; rerun required."
        elif existing.status == "completed":
            if not output_exists:
                reason = "Stage outputs are missing."
            elif existing.input_hash and current_input_hash and existing.input_hash != current_input_hash:
                reason = "Stage inputs changed since completion."
            elif existing.output_hash and current_output_hash and existing.output_hash != current_output_hash:
                reason = "Stage outputs changed since completion."
        if reason:
            upsert_stage_state(
                conn,
                project_id=project_id,
                stage_name=stage_name,
                status="stale",
                input_hash=current_input_hash,
                output_hash=current_output_hash,
                error_message=reason,
            )
            stale_stages.append(stage_name)
            downstream_is_stale = True
        else:
            downstream_is_stale = downstream_is_stale or existing.status == "stale"
    return stale_stages


def upsert_frame_state(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    frame_id: str,
    visual_slot_id: str = "",
    stage: str = DEFAULT_STAGE,
    status: str = "pending",
    prompt_hash: str = "",
    image_path: str = "",
    provider_job_id: str = "",
    error_message: str = "",
    reset_on_prompt_change: bool = True,
) -> FrameState:
    now = iso_now()
    visual_slot_id = visual_slot_id or ""
    existing = get_frame_state(conn, project_id=project_id, frame_id=frame_id, visual_slot_id=visual_slot_id, stage=stage)
    if existing is None:
        conn.execute(
            """
            INSERT INTO frame_state (
                project_id, frame_id, visual_slot_id, stage, status, attempt_count,
                prompt_hash, image_path, provider_job_id, error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, frame_id, visual_slot_id, stage, status, prompt_hash, image_path, provider_job_id, error_message, now, now),
        )
    else:
        prompt_changed = bool(prompt_hash and existing.prompt_hash and prompt_hash != existing.prompt_hash)
        if reset_on_prompt_change and prompt_changed:
            conn.execute(
                """
                UPDATE frame_state
                SET status = 'pending', attempt_count = 0, prompt_hash = ?, image_path = '', provider_job_id = '', error_message = '', updated_at = ?
                WHERE project_id = ? AND frame_id = ? AND visual_slot_id = ? AND stage = ?
                """,
                (prompt_hash, now, project_id, frame_id, visual_slot_id, stage),
            )
        else:
            conn.execute(
                """
                UPDATE frame_state
                SET prompt_hash = COALESCE(NULLIF(?, ''), prompt_hash),
                    image_path = COALESCE(NULLIF(?, ''), image_path),
                    provider_job_id = COALESCE(NULLIF(?, ''), provider_job_id),
                    error_message = CASE WHEN ? != '' THEN ? ELSE error_message END,
                    updated_at = ?
                WHERE project_id = ? AND frame_id = ? AND visual_slot_id = ? AND stage = ?
                """,
                (
                    prompt_hash,
                    image_path,
                    provider_job_id,
                    error_message,
                    error_message,
                    now,
                    project_id,
                    frame_id,
                    visual_slot_id,
                    stage,
                ),
            )
    conn.commit()
    state = get_frame_state(conn, project_id=project_id, frame_id=frame_id, visual_slot_id=visual_slot_id, stage=stage)
    assert state is not None
    return state


def mark_frame_running(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    frame_id: str,
    visual_slot_id: str = "",
    stage: str = DEFAULT_STAGE,
    prompt_hash: str = "",
    provider_job_id: str = "",
) -> FrameState:
    upsert_frame_state(
        conn,
        project_id=project_id,
        frame_id=frame_id,
        visual_slot_id=visual_slot_id,
        stage=stage,
        status="pending",
        prompt_hash=prompt_hash,
    )
    now = iso_now()
    conn.execute(
        """
        UPDATE frame_state
        SET status = 'running', attempt_count = attempt_count + 1,
            prompt_hash = COALESCE(NULLIF(?, ''), prompt_hash),
            provider_job_id = COALESCE(NULLIF(?, ''), provider_job_id),
            error_message = '', updated_at = ?
        WHERE project_id = ? AND frame_id = ? AND visual_slot_id = ? AND stage = ?
        """,
        (prompt_hash, provider_job_id, now, project_id, frame_id, visual_slot_id or "", stage),
    )
    conn.commit()
    state = get_frame_state(conn, project_id=project_id, frame_id=frame_id, visual_slot_id=visual_slot_id or "", stage=stage)
    assert state is not None
    return state


def mark_frame_success(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    frame_id: str,
    visual_slot_id: str = "",
    stage: str = DEFAULT_STAGE,
    prompt_hash: str = "",
    image_path: str = "",
    provider_job_id: str = "",
) -> FrameState:
    upsert_frame_state(
        conn,
        project_id=project_id,
        frame_id=frame_id,
        visual_slot_id=visual_slot_id,
        stage=stage,
        status="pending",
        prompt_hash=prompt_hash,
    )
    now = iso_now()
    conn.execute(
        """
        UPDATE frame_state
        SET status = 'success',
            prompt_hash = COALESCE(NULLIF(?, ''), prompt_hash),
            image_path = COALESCE(NULLIF(?, ''), image_path),
            provider_job_id = COALESCE(NULLIF(?, ''), provider_job_id),
            error_message = '', updated_at = ?
        WHERE project_id = ? AND frame_id = ? AND visual_slot_id = ? AND stage = ?
        """,
        (prompt_hash, image_path, provider_job_id, now, project_id, frame_id, visual_slot_id or "", stage),
    )
    conn.commit()
    state = get_frame_state(conn, project_id=project_id, frame_id=frame_id, visual_slot_id=visual_slot_id or "", stage=stage)
    assert state is not None
    return state


def mark_frame_failed(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    frame_id: str,
    visual_slot_id: str = "",
    stage: str = DEFAULT_STAGE,
    prompt_hash: str = "",
    provider_job_id: str = "",
    error_message: str = "",
) -> FrameState:
    upsert_frame_state(
        conn,
        project_id=project_id,
        frame_id=frame_id,
        visual_slot_id=visual_slot_id,
        stage=stage,
        status="pending",
        prompt_hash=prompt_hash,
    )
    now = iso_now()
    conn.execute(
        """
        UPDATE frame_state
        SET status = 'failed',
            prompt_hash = COALESCE(NULLIF(?, ''), prompt_hash),
            provider_job_id = COALESCE(NULLIF(?, ''), provider_job_id),
            error_message = ?, updated_at = ?
        WHERE project_id = ? AND frame_id = ? AND visual_slot_id = ? AND stage = ?
        """,
        (prompt_hash, provider_job_id, error_message, now, project_id, frame_id, visual_slot_id or "", stage),
    )
    conn.commit()
    state = get_frame_state(conn, project_id=project_id, frame_id=frame_id, visual_slot_id=visual_slot_id or "", stage=stage)
    assert state is not None
    return state


def summarize_states(states: Iterable[FrameState | sqlite3.Row]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    total = 0
    for state in states:
        total += 1
        status = str(state["status"] if isinstance(state, sqlite3.Row) else state.status)
        counts[status] = counts.get(status, 0) + 1
    return {"total": total, "by_status": dict(sorted(counts.items()))}


def state_to_dict(state: FrameState) -> dict[str, Any]:
    return {
        "project_id": state.project_id,
        "frame_id": state.frame_id,
        "visual_slot_id": state.visual_slot_id,
        "stage": state.stage,
        "status": state.status,
        "attempt_count": state.attempt_count,
        "prompt_hash": state.prompt_hash,
        "image_path": state.image_path,
        "provider_job_id": state.provider_job_id,
        "error_message": state.error_message,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def stage_state_to_dict(state: StageState) -> dict[str, Any]:
    return {
        "project_id": state.project_id,
        "stage_name": state.stage_name,
        "status": state.status,
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "input_hash": state.input_hash,
        "output_hash": state.output_hash,
        "error_message": state.error_message,
        "attempt_count": state.attempt_count,
        "updated_at": state.updated_at,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
