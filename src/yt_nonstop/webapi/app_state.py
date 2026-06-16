from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.models import (
    ArtifactEntry,
    AssetCollection,
    AssetGroup,
    ProjectOverview,
    ProjectSummary,
    ReviewDecision,
    ReviewItem,
    RunDetails,
    RunEvent,
    RunSummary,
    SessionRecord,
    SettingRecord,
    UserRecord,
    WorkspaceSummary,
)


SCHEMA_VERSION = 2


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_password(password: str, *, salt: str | None = None) -> str:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), actual_salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2_sha256$120000${actual_salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        _scheme, iterations, salt, digest = stored_hash.split("$", 3)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


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


def _review_item_id(row: dict[str, Any], fallback: str) -> str:
    for key in row.keys():
        if "id" in key.lower() and row.get(key):
            return str(row[key])
    return fallback


def _review_item_label(row: dict[str, Any], fallback: str) -> str:
    for candidate in ("text", "prompt", "shot_id", "beat_id", "warning", "action"):
        if row.get(candidate):
            return str(row[candidate])
    return fallback


@dataclass(slots=True)
class AuthSession:
    user: UserRecord
    session: SessionRecord


class AppStateStore:
    def __init__(self, config: WebConfig) -> None:
        self.config = config
        self.config.ensure_runtime_dirs()
        self.db_path = self.config.runtime_dir / "studio.sqlite3"
        self._init_db()
        self._seed_workspace()
        self._seed_default_user()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self.connect() as connection:
            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version and current_version != SCHEMA_VERSION:
                connection.execute("PRAGMA user_version = 0")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    support TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lifecycle_status TEXT NOT NULL,
                    current_stage TEXT,
                    next_stage TEXT,
                    project_json_path TEXT,
                    last_updated TEXT,
                    last_opened_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id)
                );

                CREATE TABLE IF NOT EXISTS project_snapshots (
                    project_id TEXT PRIMARY KEY,
                    blocked_count INTEGER NOT NULL DEFAULT 0,
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    available_outputs_json TEXT NOT NULL DEFAULT '[]',
                    next_command TEXT,
                    dashboard_json TEXT NOT NULL DEFAULT '{}',
                    synced_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_id INTEGER,
                    started_at TEXT,
                    finished_at TEXT,
                    exit_code INTEGER,
                    log_path TEXT NOT NULL,
                    read_only INTEGER NOT NULL DEFAULT 0,
                    error_category TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS run_locks (
                    project_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    locked_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id),
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS review_items (
                    item_key TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT,
                    warning TEXT,
                    action TEXT,
                    image_path TEXT,
                    start_value TEXT,
                    end_value TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS review_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    user_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, item_id),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS asset_indexes (
                    asset_key TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_at TEXT NOT NULL,
                    preview_kind TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS provider_configs (
                    key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    updated_by INTEGER,
                    FOREIGN KEY(updated_by) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    preference_key TEXT PRIMARY KEY,
                    user_id INTEGER,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_user_id INTEGER,
                    event_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(actor_user_id) REFERENCES users(id)
                );
                """
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute(
                """
                INSERT INTO schema_migrations (version, applied_at)
                VALUES (?, ?)
                ON CONFLICT(version) DO NOTHING
                """,
                (SCHEMA_VERSION, _iso_now()),
            )

    def _seed_workspace(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO workspaces (workspace_id, root_path, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    root_path = excluded.root_path,
                    name = excluded.name,
                    updated_at = excluded.updated_at
                """,
                ("local-default", str(self.config.workspace_root), "Local Workspace", _iso_now(), _iso_now()),
            )

    def _seed_default_user(self) -> None:
        with self.connect() as connection:
            existing = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
            if existing and int(existing["count"]) > 0:
                return
            now = _iso_now()
            connection.execute(
                """
                INSERT INTO users (username, display_name, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    self.config.default_operator_username,
                    "Local Operator",
                    _hash_password(self.config.default_operator_password),
                    "Admin",
                    now,
                    now,
                ),
            )

    def authenticate(self, username: str, password: str) -> AuthSession | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
            payload = _row_to_dict(row)
            if not payload or not _verify_password(password, payload["password_hash"]):
                return None
            user = self._user_from_row(payload)
            session = self._create_session(connection, user.id)
            self.record_audit_event(
                actor_user_id=user.id,
                event_type="login",
                target_type="session",
                target_id=session.token,
                payload={},
                connection=connection,
            )
            return AuthSession(user=user, session=session)

    def _create_session(self, connection: sqlite3.Connection, user_id: int) -> SessionRecord:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.config.session_ttl_hours)
        token = secrets.token_urlsafe(32)
        payload = SessionRecord(
            token=token,
            user_id=user_id,
            created_at=now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            expires_at=expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            last_seen_at=now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        connection.execute(
            """
            INSERT INTO sessions (token, user_id, created_at, expires_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (payload.token, payload.user_id, payload.created_at, payload.expires_at, payload.last_seen_at),
        )
        return payload

    def get_session(self, token: str) -> AuthSession | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT s.token, s.user_id, s.created_at, s.expires_at, s.last_seen_at,
                       u.id AS uid, u.username, u.display_name, u.role, u.is_active, u.created_at AS user_created_at, u.updated_at AS user_updated_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            if row is None:
                return None
            now = datetime.now(timezone.utc)
            expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            if expires_at <= now or not int(row["is_active"]):
                connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
            last_seen = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            connection.execute("UPDATE sessions SET last_seen_at = ? WHERE token = ?", (last_seen, token))
            user = UserRecord(
                id=int(row["uid"]),
                username=str(row["username"]),
                display_name=str(row["display_name"]),
                role=str(row["role"]),
                is_active=bool(row["is_active"]),
                created_at=str(row["user_created_at"]),
                updated_at=str(row["user_updated_at"]),
            )
            session = SessionRecord(
                token=str(row["token"]),
                user_id=int(row["user_id"]),
                created_at=str(row["created_at"]),
                expires_at=str(row["expires_at"]),
                last_seen_at=last_seen,
            )
            return AuthSession(user=user, session=session)

    def logout(self, token: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def sync_projects(self, projects: list[ProjectSummary]) -> None:
        now = _iso_now()
        with self.connect() as connection:
            for item in projects:
                lifecycle_status = item.lifecycle_status or ("draft" if item.support == "limited" else "ready_for_validation")
                connection.execute(
                    """
                    INSERT INTO projects (
                        project_id, workspace_id, name, path, kind, support, status, lifecycle_status,
                        current_stage, next_stage, project_json_path, last_updated, created_at, updated_at
                    )
                    VALUES (?, 'local-default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        name = excluded.name,
                        path = excluded.path,
                        kind = excluded.kind,
                        support = excluded.support,
                        status = excluded.status,
                        lifecycle_status = excluded.lifecycle_status,
                        current_stage = excluded.current_stage,
                        next_stage = excluded.next_stage,
                        project_json_path = excluded.project_json_path,
                        last_updated = excluded.last_updated,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item.id,
                        item.name,
                        item.path,
                        item.kind,
                        item.support,
                        item.status,
                        lifecycle_status,
                        item.current_stage,
                        item.next_stage,
                        item.project_json_path,
                        item.last_updated,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO project_snapshots (project_id, blocked_count, warning_count, available_outputs_json, synced_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        blocked_count = excluded.blocked_count,
                        warning_count = excluded.warning_count,
                        available_outputs_json = excluded.available_outputs_json,
                        synced_at = excluded.synced_at
                    """,
                    (item.id, item.blocked_count, item.warning_count, _json_dump(item.available_outputs), now),
                )

    def update_project_snapshot(self, *, project_id: str, lifecycle_status: str, next_command: str | None, dashboard: dict[str, Any], blocked_count: int, warning_count: int, available_outputs: list[str]) -> None:
        now = _iso_now()
        with self.connect() as connection:
            connection.execute("UPDATE projects SET lifecycle_status = ?, updated_at = ? WHERE project_id = ?", (lifecycle_status, now, project_id))
            connection.execute(
                """
                INSERT INTO project_snapshots (project_id, blocked_count, warning_count, available_outputs_json, next_command, dashboard_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    blocked_count = excluded.blocked_count,
                    warning_count = excluded.warning_count,
                    available_outputs_json = excluded.available_outputs_json,
                    next_command = excluded.next_command,
                    dashboard_json = excluded.dashboard_json,
                    synced_at = excluded.synced_at
                """,
                (project_id, blocked_count, warning_count, _json_dump(available_outputs), next_command, _json_dump(dashboard), now),
            )

    def touch_project(self, project_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE projects SET last_opened_at = ?, updated_at = ? WHERE project_id = ?", (_iso_now(), _iso_now(), project_id))

    def record_run(self, run: RunSummary, *, user_id: int | None = None, error_category: str | None = None) -> None:
        now = _iso_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, project_id, action_type, command_json, status, user_id, started_at, finished_at, exit_code, log_path, read_only, error_category, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    action_type = excluded.action_type,
                    command_json = excluded.command_json,
                    status = excluded.status,
                    user_id = COALESCE(excluded.user_id, runs.user_id),
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    exit_code = excluded.exit_code,
                    log_path = excluded.log_path,
                    read_only = excluded.read_only,
                    error_category = excluded.error_category,
                    updated_at = excluded.updated_at
                """,
                (
                    run.run_id,
                    run.project_id,
                    run.action_type,
                    _json_dump(run.command),
                    run.status,
                    user_id or run.user_id,
                    run.started_at,
                    run.finished_at,
                    run.exit_code,
                    run.log_path,
                    1 if run.read_only else 0,
                    error_category or run.error_category,
                    now,
                    now,
                ),
            )
            if not run.read_only and run.status in {"queued", "running"}:
                connection.execute(
                    """
                    INSERT INTO run_locks (project_id, run_id, locked_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        run_id = excluded.run_id,
                        locked_at = excluded.locked_at
                    """,
                    (run.project_id, run.run_id, now),
                )
            if run.status in {"completed", "failed", "rejected", "cancelled"}:
                connection.execute("DELETE FROM run_locks WHERE project_id = ? AND run_id = ?", (run.project_id, run.run_id))

    def record_run_event(self, run_id: str, *, event_type: str, message: str) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO run_events (run_id, event_type, message, created_at) VALUES (?, ?, ?, ?)", (run_id, event_type, message, _iso_now()))

    def get_run(self, run_id: str, *, log_tail: list[str] | None = None) -> RunDetails:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, u.username
                FROM runs r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            events = connection.execute("SELECT id, run_id, event_type, message, created_at FROM run_events WHERE run_id = ? ORDER BY id ASC", (run_id,)).fetchall()
        summary = self._run_from_row(_row_to_dict(row) or {})
        return RunDetails(
            **summary.model_dump(),
            events=[RunEvent(event_id=int(item["id"]), run_id=str(item["run_id"]), event_type=str(item["event_type"]), message=str(item["message"]), created_at=str(item["created_at"])) for item in events],
            log_tail=log_tail or [],
        )

    def list_runs(self, *, project_id: str | None = None, limit: int = 50) -> list[RunSummary]:
        query = """
            SELECT r.*, u.username
            FROM runs r
            LEFT JOIN users u ON u.id = r.user_id
        """
        params: list[Any] = []
        if project_id:
            query += " WHERE r.project_id = ?"
            params.append(project_id)
        query += " ORDER BY COALESCE(r.started_at, r.created_at) DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._run_from_row(_row_to_dict(row) or {}) for row in rows]

    def sync_review_items(self, *, project_id: str, source: str, rows: list[dict[str, Any]]) -> list[ReviewItem]:
        now = _iso_now()
        items: list[ReviewItem] = []
        with self.connect() as connection:
            for index, row in enumerate(rows):
                item_id = _review_item_id(row, f"{project_id}-{index:04d}")
                item = ReviewItem(
                    item_id=item_id,
                    label=_review_item_label(row, item_id),
                    source=source,
                    status=str(row.get("status")) if row.get("status") is not None else None,
                    warning=str(row.get("warning")) if row.get("warning") is not None else None,
                    action=str(row.get("action")) if row.get("action") is not None else None,
                    image_path=str(row.get("image_path")) if row.get("image_path") is not None else None,
                    start=str(row.get("start")) if row.get("start") is not None else None,
                    end=str(row.get("end")) if row.get("end") is not None else None,
                    payload=row,
                )
                items.append(item)
                connection.execute(
                    """
                    INSERT INTO review_items (item_key, project_id, item_id, source, label, status, warning, action, image_path, start_value, end_value, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_key) DO UPDATE SET
                        label = excluded.label,
                        status = excluded.status,
                        warning = excluded.warning,
                        action = excluded.action,
                        image_path = excluded.image_path,
                        start_value = excluded.start_value,
                        end_value = excluded.end_value,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (f"{project_id}:{item_id}", project_id, item_id, source, item.label, item.status, item.warning, item.action, item.image_path, item.start, item.end, _json_dump(row), now),
                )
        return items

    def list_review_items(self, project_id: str) -> list[ReviewItem]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT item_id, label, source, status, warning, action, image_path, start_value, end_value, payload_json
                FROM review_items
                WHERE project_id = ?
                ORDER BY updated_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [
            ReviewItem(
                item_id=str(row["item_id"]),
                label=str(row["label"]),
                source=str(row["source"]),
                status=row["status"],
                warning=row["warning"],
                action=row["action"],
                image_path=row["image_path"],
                start=row["start_value"],
                end=row["end_value"],
                payload=_json_load(row["payload_json"], {}),
            )
            for row in rows
        ]

    def list_review_decisions(self, project_id: str) -> list[ReviewDecision]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT rd.*, u.username
                FROM review_decisions rd
                LEFT JOIN users u ON u.id = rd.user_id
                WHERE rd.project_id = ?
                ORDER BY rd.updated_at DESC, rd.id DESC
                """,
                (project_id,),
            ).fetchall()
        return [self._review_decision_from_row(_row_to_dict(row) or {}) for row in rows]

    def save_review_decision(
        self,
        *,
        project_id: str,
        item_id: str,
        source: str,
        decision: str,
        note: str,
        payload: dict[str, Any],
        user_id: int | None,
    ) -> ReviewDecision:
        now = _iso_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO review_decisions (project_id, item_id, source, decision, note, payload_json, user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, item_id) DO UPDATE SET
                    source = excluded.source,
                    decision = excluded.decision,
                    note = excluded.note,
                    payload_json = excluded.payload_json,
                    user_id = excluded.user_id,
                    updated_at = excluded.updated_at
                """,
                (project_id, item_id, source, decision, note, _json_dump(payload), user_id, now, now),
            )
            row = connection.execute(
                """
                SELECT rd.*, u.username
                FROM review_decisions rd
                LEFT JOIN users u ON u.id = rd.user_id
                WHERE rd.project_id = ? AND rd.item_id = ?
                """,
                (project_id, item_id),
            ).fetchone()
        self.record_audit_event(actor_user_id=user_id, event_type="review_decision_saved", target_type="review_item", target_id=f"{project_id}:{item_id}", payload={"decision": decision})
        return self._review_decision_from_row(_row_to_dict(row) or {})

    def sync_asset_index(self, *, project_id: str, entries: list[ArtifactEntry]) -> AssetCollection:
        now = _iso_now()
        with self.connect() as connection:
            for item in entries:
                connection.execute(
                    """
                    INSERT INTO asset_indexes (asset_key, project_id, type, label, path, size, modified_at, preview_kind, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_key) DO UPDATE SET
                        type = excluded.type,
                        label = excluded.label,
                        path = excluded.path,
                        size = excluded.size,
                        modified_at = excluded.modified_at,
                        preview_kind = excluded.preview_kind,
                        updated_at = excluded.updated_at
                    """,
                    (f"{project_id}:{item.path}", project_id, item.type, item.label, item.path, item.size, item.modified_at, item.preview_kind, now),
                )
        return self.list_asset_collection(project_id)

    def list_asset_collection(self, project_id: str) -> AssetCollection:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT type, label, path, size, modified_at, preview_kind
                FROM asset_indexes
                WHERE project_id = ?
                ORDER BY type ASC, modified_at DESC
                """,
                (project_id,),
            ).fetchall()
        grouped: dict[str, list[ArtifactEntry]] = {}
        for row in rows:
            entry = ArtifactEntry(
                type=str(row["type"]),
                label=str(row["label"]),
                path=str(row["path"]),
                size=int(row["size"]),
                modified_at=str(row["modified_at"]),
                preview_kind=str(row["preview_kind"]),
            )
            grouped.setdefault(entry.type, []).append(entry)
        groups = [AssetGroup(type=key, label=key.replace("_", " ").title(), count=len(values), entries=values) for key, values in grouped.items()]
        return AssetCollection(project_id=project_id, total_count=sum(group.count for group in groups), groups=groups)

    def get_settings(self) -> list[SettingRecord]:
        with self.connect() as connection:
            provider_rows = connection.execute("SELECT pc.*, u.username FROM provider_configs pc LEFT JOIN users u ON u.id = pc.updated_by ORDER BY pc.provider, pc.key").fetchall()
            preference_rows = connection.execute("SELECT * FROM user_preferences ORDER BY preference_key").fetchall()
        items = [
            SettingRecord(
                category="provider_metadata",
                key=str(row["key"]),
                provider=str(row["provider"]),
                value=_json_load(row["value_json"], {}),
                updated_at=str(row["updated_at"]),
                updated_by_username=row["username"],
            )
            for row in provider_rows
        ]
        items.extend(
            [
                SettingRecord(
                    category="operator_preferences",
                    key=str(row["preference_key"]),
                    provider=None,
                    value=_json_load(row["value_json"], {}),
                    updated_at=str(row["updated_at"]),
                    updated_by_username=None,
                )
                for row in preference_rows
            ]
        )
        items.append(
            SettingRecord(
                category="workspace",
                key="workspace",
                provider="studio",
                value={
                    "workspace_root": str(self.config.workspace_root),
                    "runtime_dir": str(self.config.runtime_dir),
                    "default_poll_interval": self.config.default_poll_interval,
                },
                updated_at=_iso_now(),
                updated_by_username="system",
            )
        )
        items.append(
            SettingRecord(
                category="provider_metadata",
                key="fastgen",
                provider="fastgen",
                value={
                    "api_url": self.config.fastgen_api_url,
                    "model": self.config.fastgen_model,
                    "api_key_configured": bool(self.config.fastgen_api_key),
                    "secret_storage": "environment",
                },
                updated_at=_iso_now(),
                updated_by_username="system",
            )
        )
        items.append(
            SettingRecord(
                category="environment",
                key="environment",
                provider="studio",
                value={
                    "default_profile": self.config.default_profile,
                    "default_concurrency": self.config.default_concurrency,
                },
                updated_at=_iso_now(),
                updated_by_username="system",
            )
        )
        items.append(
            SettingRecord(
                category="auth",
                key="local_operator",
                provider="studio",
                value={
                    "username": self.config.default_operator_username,
                    "role": "Admin",
                    "session_ttl_hours": self.config.session_ttl_hours,
                    "default_credentials_active": self.config.default_operator_username == "operator"
                    and self.config.default_operator_password == "operator",
                },
                updated_at=_iso_now(),
                updated_by_username="system",
            )
        )
        return items

    def upsert_provider_config(self, *, key: str, provider: str, value: dict[str, Any], updated_by: int | None) -> SettingRecord:
        now = _iso_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO provider_configs (key, provider, value_json, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    provider = excluded.provider,
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (key, provider, _json_dump(value), now, updated_by),
            )
            row = connection.execute(
                """
                SELECT pc.*, u.username
                FROM provider_configs pc
                LEFT JOIN users u ON u.id = pc.updated_by
                WHERE pc.key = ?
                """,
                (key,),
            ).fetchone()
        self.record_audit_event(actor_user_id=updated_by, event_type="provider_config_updated", target_type="provider_config", target_id=key, payload=value)
        payload = _row_to_dict(row) or {}
        return SettingRecord(
            category="provider_metadata",
            key=str(payload["key"]),
            provider=str(payload["provider"]),
            value=_json_load(payload.get("value_json"), {}),
            updated_at=str(payload["updated_at"]),
            updated_by_username=payload.get("username"),
        )

    def upsert_user_preference(self, *, key: str, value: dict[str, Any], user_id: int | None) -> SettingRecord:
        now = _iso_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO user_preferences (preference_key, user_id, value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(preference_key) DO UPDATE SET
                    user_id = excluded.user_id,
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, user_id, _json_dump(value), now),
            )
        self.record_audit_event(actor_user_id=user_id, event_type="user_preference_updated", target_type="user_preference", target_id=key, payload=value)
        return SettingRecord(category="operator_preferences", key=key, provider=None, value=value, updated_at=now, updated_by_username=None)

    def build_workspace_summary(self, projects: list[ProjectSummary]) -> WorkspaceSummary:
        with self.connect() as connection:
            active_runs = int(connection.execute("SELECT COUNT(*) AS count FROM runs WHERE status IN ('queued', 'running')").fetchone()["count"])
        return WorkspaceSummary(
            workspace_root=str(self.config.workspace_root),
            total_projects=len(projects),
            full_support_projects=sum(1 for item in projects if item.support == "full"),
            limited_support_projects=sum(1 for item in projects if item.support == "limited"),
            active_runs=active_runs,
            blocked_projects=sum(1 for item in projects if item.lifecycle_status == "blocked"),
            awaiting_review_projects=sum(1 for item in projects if item.lifecycle_status == "awaiting_review"),
            ready_for_render_projects=sum(1 for item in projects if item.lifecycle_status == "ready_for_render"),
            completed_projects=sum(1 for item in projects if item.lifecycle_status == "completed"),
            recent_project_ids=[item.id for item in sorted(projects, key=lambda row: row.last_updated or "", reverse=True)[:5]],
        )

    def build_project_overview(
        self,
        *,
        project: ProjectSummary,
        lifecycle_status: str,
        pipeline_state: dict[str, Any],
        latest_outputs: list[str],
    ) -> ProjectOverview:
        recent_runs = self.list_runs(project_id=project.id, limit=10)
        review_decisions = self.list_review_decisions(project.id)
        latest_run = recent_runs[0] if recent_runs else None
        return ProjectOverview(
            project_id=project.id,
            project_name=project.name,
            path=project.path,
            kind=project.kind,
            support=project.support,
            lifecycle_status=lifecycle_status,
            current_stage=pipeline_state.get("current_stage"),
            next_stage=pipeline_state.get("next_stage"),
            next_command=pipeline_state.get("next_command"),
            blocked=pipeline_state.get("blocked", []),
            warnings=pipeline_state.get("warnings", []),
            latest_outputs=latest_outputs,
            latest_run=latest_run,
            recent_runs=recent_runs,
            review_decision_count=len(review_decisions),
            active_run=pipeline_state.get("active_run"),
        )

    def record_audit_event(
        self,
        *,
        actor_user_id: int | None,
        event_type: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any],
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is not None:
            connection.execute(
                """
                INSERT INTO audit_events (actor_user_id, event_type, target_type, target_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (actor_user_id, event_type, target_type, target_id, _json_dump(payload), _iso_now()),
            )
            return
        with self.connect() as owned_connection:
            owned_connection.execute(
                """
                INSERT INTO audit_events (actor_user_id, event_type, target_type, target_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (actor_user_id, event_type, target_type, target_id, _json_dump(payload), _iso_now()),
            )

    def _user_from_row(self, payload: dict[str, Any]) -> UserRecord:
        return UserRecord(
            id=int(payload["id"]),
            username=str(payload["username"]),
            display_name=str(payload["display_name"]),
            role=str(payload["role"]),
            is_active=bool(payload["is_active"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )

    def _run_from_row(self, payload: dict[str, Any]) -> RunSummary:
        return RunSummary(
            run_id=str(payload["run_id"]),
            project_id=str(payload["project_id"]),
            action_type=str(payload["action_type"]),
            command=_json_load(payload.get("command_json"), []),
            status=str(payload["status"]),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            exit_code=payload.get("exit_code"),
            log_path=str(payload["log_path"]),
            read_only=bool(payload.get("read_only")),
            user_id=payload.get("user_id"),
            username=payload.get("username"),
            error_category=payload.get("error_category"),
        )

    def _review_decision_from_row(self, payload: dict[str, Any]) -> ReviewDecision:
        return ReviewDecision(
            id=int(payload["id"]),
            project_id=str(payload["project_id"]),
            item_id=str(payload["item_id"]),
            source=str(payload["source"]),
            decision=str(payload["decision"]),
            note=str(payload.get("note") or ""),
            payload=_json_load(payload.get("payload_json"), {}),
            user_id=payload.get("user_id"),
            username=payload.get("username"),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )


def lifecycle_status_for(*, support: str, blocked: list[str], ready_for_render: bool, ready_for_human_review: bool, completed: bool, active_run: RunSummary | None, next_stage: str | None) -> str:
    if active_run:
        return "rendering" if next_stage == "render" else "running"
    if completed:
        return "completed"
    if blocked:
        return "blocked"
    if ready_for_render:
        return "ready_for_render"
    if ready_for_human_review:
        return "awaiting_review"
    if support == "limited":
        return "draft"
    return "ready_for_validation"
