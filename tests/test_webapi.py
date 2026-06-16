from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from yt_nonstop.webapi.app import create_app
from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.jobs import JobStore
from yt_nonstop.webapi.project_discovery import discover_projects


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_repo_native_project(root: Path) -> Path:
    project_root = root / "demo_project"
    for folder in ("input", "work", "images", "final_images", "output", "renders", "qc", "reports", "prompts", "exports", "logs"):
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    _write_json(
        project_root / "project.json",
        {
            "project_id": "demo-project",
            "project_name": "Demo Project",
            "inputs": {},
            "workflow": {},
            "runtime": {},
        },
    )
    (project_root / "work" / "review_sheet.csv").write_text("beat_id,text\nB0001,hello\n", encoding="utf-8")
    (project_root / "exports" / "edit_timeline.csv").write_text("shot_id,start,end\nS001,0,3\n", encoding="utf-8")
    (project_root / "reports" / "notes.md").write_text("# hello\nworld\n", encoding="utf-8")
    (project_root / "prompts" / "prompts.md").write_text("# prompt\nvisual direction\n", encoding="utf-8")
    (project_root / "images" / "B0001.png").write_bytes(b"image")
    (project_root / "final_images" / "B0001.png").write_bytes(b"final")
    (project_root / "output" / "final.mp4").write_bytes(b"video")
    return project_root


def _make_artifact_project(root: Path) -> Path:
    project_root = root / "artifact_project"
    for folder in ("input", "work", "images", "output"):
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    (project_root / "work" / "timeline.csv").write_text("shot_id,start,end\nS002,3,6\n", encoding="utf-8")
    return project_root


def _login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "operator", "password": "operator"})
    assert response.status_code == 200
    token = response.json()["session"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_auth_rejects_invalid_login_and_protects_routes(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)

    invalid_login = client.post("/api/auth/login", json={"username": "operator", "password": "wrong"})
    assert invalid_login.status_code == 401
    assert invalid_login.json()["code"] == "auth_error"

    protected = client.get("/api/projects")
    assert protected.status_code == 401
    assert protected.json()["code"] == "auth_error"


def test_auth_logout_invalidates_session(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)
    headers = _login(client)

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200

    logout = client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 200

    after_logout = client.get("/api/auth/me", headers=headers)
    assert after_logout.status_code == 401
    assert after_logout.json()["code"] == "auth_error"


def test_auth_expires_sessions(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("YT_NONSTOP_STUDIO_SESSION_TTL_HOURS", "-1")

    app = create_app()
    client = TestClient(app)
    headers = _login(client)

    expired = client.get("/api/auth/me", headers=headers)
    assert expired.status_code == 401
    assert expired.json()["code"] == "auth_error"


def test_project_discovery_handles_repo_and_artifact_projects(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _make_repo_native_project(workspace)
    _make_artifact_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))
    config = WebConfig.from_env()

    projects = discover_projects(config)
    assert {item.kind for item in projects} == {"repo-native", "artifact-workspace"}
    assert any(item.support == "full" for item in projects)
    assert any(item.support == "limited" for item in projects)


def test_job_store_rejects_conflicting_write_jobs(tmp_path):
    config = WebConfig(
        repo_root=tmp_path,
        workspace_root=tmp_path,
        runtime_dir=tmp_path / "runtime",
        allowed_project_roots=[tmp_path],
        default_poll_interval=1.0,
        default_operator_username="operator",
        default_operator_password="operator",
        session_ttl_hours=12,
        default_profile="no_vlm_production",
        default_concurrency=10,
        fastgen_api_url="",
        fastgen_model="",
        fastgen_api_key="",
    )
    store = JobStore(config)
    accepted = store.start_job(
        project_id="demo",
        command=[sys.executable, "-c", "import time; print('one'); time.sleep(0.5)"],
        read_only=False,
    )
    rejected = store.start_job(
        project_id="demo",
        command=[sys.executable, "-c", "print('two')"],
        read_only=False,
    )
    assert accepted.accepted is True
    assert rejected.accepted is False
    time.sleep(0.8)
    finished = store.get_job(accepted.job.run_id)
    assert finished.status == "completed"


def test_webapi_workspace_projects_and_assets(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project_root = _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)
    headers = _login(client)

    summary = client.get("/api/workspace/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total_projects"] == 1

    projects = client.get("/api/projects", headers=headers)
    assert projects.status_code == 200
    payload = projects.json()
    assert len(payload) == 1
    project_id = payload[0]["id"]

    details = client.get(f"/api/projects/{project_id}", headers=headers)
    assert details.status_code == 200
    assert details.json()["name"] == "Demo Project"

    overview = client.get(f"/api/projects/{project_id}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["project_id"] == "demo-project"

    assets = client.get(f"/api/projects/{project_id}/assets", headers=headers)
    assert assets.status_code == 200
    asset_payload = assets.json()
    assert asset_payload["total_count"] >= 5
    groups = {item["type"]: item for item in asset_payload["groups"]}
    assert {"images", "final_images", "output", "prompts", "reports"}.issubset(groups.keys())
    assert groups["final_images"]["label"] == "Final Images"

    timeline = client.get(f"/api/projects/{project_id}/timeline", headers=headers)
    assert timeline.status_code == 200
    assert timeline.json()["rows"][0]["shot_id"] == "S001"

    preview = client.get(f"/api/projects/{project_id}/preview", params={"path": str(project_root / "reports" / "notes.md")}, headers=headers)
    assert preview.status_code == 200
    assert "world" in preview.json()["content"]

    image_preview = client.get(f"/api/projects/{project_id}/preview", params={"path": str(project_root / "images" / "B0001.png")}, headers=headers)
    assert image_preview.status_code == 200
    assert image_preview.json()["preview_kind"] == "image"

    missing_preview = client.get(f"/api/projects/{project_id}/preview", params={"path": str(project_root / "reports" / "missing.md")}, headers=headers)
    assert missing_preview.status_code == 404
    assert missing_preview.json()["code"] == "filesystem_error"

    outside_file = tmp_path / "outside.md"
    outside_file.write_text("outside", encoding="utf-8")
    outside_preview = client.get(f"/api/projects/{project_id}/preview", params={"path": str(outside_file)}, headers=headers)
    assert outside_preview.status_code == 403
    assert outside_preview.json()["code"] == "filesystem_error"

    outside_media = client.get(f"/api/projects/{project_id}/media", params={"path": str(outside_file), "token": headers["Authorization"].split(" ", 1)[1]})
    assert outside_media.status_code == 403
    assert outside_media.json()["code"] == "filesystem_error"


def test_webapi_pipeline_state_marks_limited_support_actions(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _make_artifact_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)
    headers = _login(client)
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]

    pipeline_state = client.get(f"/api/projects/{project_id}/pipeline", headers=headers)
    assert pipeline_state.status_code == 200
    payload = pipeline_state.json()
    assert payload["support"] == "limited"
    assert payload["lifecycle_status"] == "blocked"
    assert payload["available_actions"]
    assert all(item["enabled"] is False for item in payload["available_actions"])
    assert all("project.json" in item["reason"] for item in payload["available_actions"])


def test_webapi_pipeline_state_marks_active_run_lock(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)
    headers = _login(client)
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]

    active_job = app.state.jobs.start_job(
        project_id=project_id,
        command=[sys.executable, "-c", "import time; time.sleep(1)"],
        read_only=False,
    )
    assert active_job.accepted is True

    pipeline_state = client.get(f"/api/projects/{project_id}/pipeline", headers=headers)
    assert pipeline_state.status_code == 200
    payload = pipeline_state.json()
    assert payload["blocked_by_active_run"] is True
    assert payload["active_run"]["run_id"] == active_job.job.run_id
    assert all(item["enabled"] is False for item in payload["available_actions"])
    assert any(active_job.job.run_id in item["reason"] for item in payload["available_actions"])


def test_webapi_runs_record_events_logs_and_rejected_conflicts(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)
    headers = _login(client)
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]

    completed_job = app.state.jobs.start_job(
        project_id=project_id,
        command=[sys.executable, "-c", "print('hello from run')"],
        read_only=False,
    )
    assert completed_job.accepted is True
    time.sleep(0.8)

    run_details = client.get(f"/api/runs/{completed_job.job.run_id}", headers=headers)
    assert run_details.status_code == 200
    completed_payload = run_details.json()
    assert completed_payload["status"] == "completed"
    assert "hello from run" in "\n".join(completed_payload["log_tail"])
    assert {event["event_type"] for event in completed_payload["events"]} >= {"queued", "running", "completed"}

    active_job = app.state.jobs.start_job(
        project_id=project_id,
        command=[sys.executable, "-c", "import time; time.sleep(1)"],
        read_only=False,
    )
    rejected_job = app.state.jobs.start_job(
        project_id=project_id,
        command=[sys.executable, "-c", "print('blocked')"],
        read_only=False,
    )
    assert active_job.accepted is True
    assert rejected_job.accepted is False

    rejected_details = client.get(f"/api/runs/{rejected_job.job.run_id}", headers=headers)
    assert rejected_details.status_code == 200
    rejected_payload = rejected_details.json()
    assert rejected_payload["status"] == "rejected"
    assert rejected_payload["error_category"] == "run_conflict_error"
    assert any("active run" in event["message"] for event in rejected_payload["events"])

    project_runs = client.get(f"/api/projects/{project_id}/runs", headers=headers)
    assert project_runs.status_code == 200
    run_ids = [item["run_id"] for item in project_runs.json()]
    assert rejected_job.job.run_id in run_ids
    assert completed_job.job.run_id in run_ids

    logs = client.get(f"/api/runs/{completed_job.job.run_id}/logs", headers=headers)
    assert logs.status_code == 200
    assert "hello from run" in "\n".join(logs.json()["lines"])


def test_webapi_pipeline_runs_review_and_settings(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    source_project = _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("FASTGEN_API_URL", "https://fastgen.example/api")
    monkeypatch.setenv("FASTGEN_MODEL", "fastgen-test")
    monkeypatch.setenv("FASTGEN_API_KEY", "super-secret-fastgen-key")

    app = create_app()
    client = TestClient(app)
    headers = _login(client)
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]

    pipeline_state = client.get(f"/api/projects/{project_id}/pipeline", headers=headers)
    assert pipeline_state.status_code == 200
    state_payload = pipeline_state.json()
    assert state_payload["project_id"] == "demo-project"
    assert "available_actions" in state_payload

    action = client.post(
        f"/api/projects/{project_id}/pipeline/actions",
        json={"action": "validate", "to_stage": "render", "concurrency": 10},
        headers=headers,
    )
    assert action.status_code == 200
    assert action.json()["accepted"] is True
    run_id = action.json()["run_id"]

    run_details = client.get(f"/api/runs/{run_id}", headers=headers)
    assert run_details.status_code == 200
    assert run_details.json()["run_id"] == run_id

    runs = client.get(f"/api/projects/{project_id}/runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json()

    review = client.get(f"/api/projects/{project_id}/review", headers=headers)
    assert review.status_code == 200
    assert review.json()["items"][0]["item_id"] == "B0001"

    decision = client.post(
        f"/api/projects/{project_id}/review/decisions",
        json={"item_id": "B0001", "source": "review_sheet.csv", "decision": "approved", "note": "Looks good"},
        headers=headers,
    )
    assert decision.status_code == 200
    assert decision.json()["decision"] == "approved"

    review_after = client.get(f"/api/projects/{project_id}/review", headers=headers)
    assert review_after.status_code == 200
    assert review_after.json()["decisions"][0]["item_id"] == "B0001"
    assert review_after.json()["summary"]["approved"] == 1

    settings = client.get("/api/settings", headers=headers)
    assert settings.status_code == 200
    settings_text = json.dumps(settings.json())
    assert "super-secret-fastgen-key" not in settings_text
    assert any(item["category"] == "environment" for item in settings.json())
    provider_settings = next(item for item in settings.json() if item["category"] == "provider_metadata" and item["provider"] == "fastgen")
    assert provider_settings["value"]["api_key_configured"] is True
    assert provider_settings["value"]["api_url"] == "https://fastgen.example/api"
    auth_settings = next(item for item in settings.json() if item["category"] == "auth")
    assert auth_settings["value"]["default_credentials_active"] is True
    assert "password" not in json.dumps(auth_settings["value"])

    update = client.patch("/api/settings", json={"default_profile": "no_vlm_production", "default_concurrency": 6}, headers=headers)
    assert update.status_code == 200
    assert update.json()["value"]["default_concurrency"] == 6
    persisted = client.get("/api/settings", headers=headers)
    preference_settings = next(item for item in persisted.json() if item["category"] == "operator_preferences" and item["key"] == "studio_preferences")
    assert preference_settings["value"]["default_concurrency"] == 6

    invalid_update = client.patch("/api/settings", json={"default_concurrency": 0}, headers=headers)
    assert invalid_update.status_code == 422

    preview_media = client.get(
        f"/api/projects/{project_id}/media",
        params={"path": str(source_project / "reports" / "notes.md"), "token": headers["Authorization"].split(" ", 1)[1]},
    )
    assert preview_media.status_code == 200


def test_webapi_can_bootstrap_project(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    source_srt = tmp_path / "source.srt"
    source_audio = tmp_path / "source.mp3"
    raw_text = tmp_path / "raw_text.md"
    source_srt.write_text("1\n00:00:00,000 --> 00:00:03,000\nHello world\n", encoding="utf-8")
    source_audio.write_bytes(b"fake audio")
    raw_text.write_text("# raw\nhello\n", encoding="utf-8")
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)
    headers = _login(client)
    invalid_response = client.post(
        "/api/projects",
        json={
            "project_name": "Invalid Web MVP",
            "source_srt_path": str(source_srt),
            "raw_text_path": str(raw_text),
        },
        headers=headers,
    )
    assert invalid_response.status_code == 400
    assert invalid_response.json()["code"] == "validation_error"
    assert not (workspace / "invalid_web_mvp").exists()

    response = client.post(
        "/api/projects",
        json={
            "project_name": "My Web MVP",
            "source_srt_path": str(source_srt),
            "source_audio_path": str(source_audio),
            "raw_text_path": str(raw_text),
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    project_root = Path(payload["project_root"])
    assert payload["next_route"] == f"/projects/{payload['project_id']}/overview"
    assert (project_root / "project.json").exists()
    assert (project_root / "input" / "raw_text.md").read_text(encoding="utf-8").startswith("# raw")

    projects = client.get("/api/projects", headers=headers)
    assert projects.status_code == 200
    assert any(item["id"] == payload["project_id"] for item in projects.json())


def test_webapi_can_create_project_from_uploaded_sources(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)
    headers = _login(client)

    response = client.post(
        "/api/projects/intake",
        data={"project_name": "Uploaded Web Project", "profile": "no_vlm_production"},
        files={
            "source_srt": ("source.srt", b"1\n00:00:00,000 --> 00:00:03,000\nHello upload\n", "text/plain"),
            "source_audio": ("source.mp3", b"fake audio", "audio/mpeg"),
            "raw_text": ("raw_text.md", b"# raw upload\nhello\n", "text/markdown"),
            "setup_notes": ("style.md", b"# style\nnoir documentary\n", "text/markdown"),
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    project_root = Path(payload["project_root"])
    assert payload["next_route"] == f"/projects/{payload['project_id']}/overview"
    assert (project_root / "project.json").exists()
    assert (project_root / "input" / "source.srt").exists()
    assert (project_root / "input" / "raw_text.md").read_text(encoding="utf-8").startswith("# raw upload")
    assert (project_root / "input" / "project_setup_notes.md").read_text(encoding="utf-8").startswith("# style")

    projects = client.get("/api/projects", headers=headers)
    assert any(item["id"] == payload["project_id"] for item in projects.json())
