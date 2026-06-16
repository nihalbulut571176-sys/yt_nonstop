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
    for folder in ("input", "work", "images", "output", "renders", "qc", "reports", "prompts", "exports", "logs"):
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
    return project_root


def _make_artifact_project(root: Path) -> Path:
    project_root = root / "artifact_project"
    for folder in ("input", "work", "images", "output"):
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    (project_root / "work" / "timeline.csv").write_text("shot_id,start,end\nS002,3,6\n", encoding="utf-8")
    return project_root


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
    finished = store.get_job(accepted.job.job_id)
    assert finished.status == "completed"


def test_webapi_endpoints_expose_projects_and_artifacts(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project_root = _make_repo_native_project(workspace)
    monkeypatch.setenv("YT_NONSTOP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", str(workspace))
    monkeypatch.setenv("YT_NONSTOP_WEB_RUNTIME_DIR", str(tmp_path / "runtime"))

    app = create_app()
    client = TestClient(app)

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    payload = projects.json()
    assert len(payload) == 1
    project_id = payload[0]["id"]

    details = client.get(f"/api/projects/{project_id}")
    assert details.status_code == 200
    assert details.json()["name"] == "Demo Project"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts")
    assert artifacts.status_code == 200
    assert any(item["label"].endswith("notes.md") for item in artifacts.json())

    timeline = client.get(f"/api/projects/{project_id}/timeline")
    assert timeline.status_code == 200
    assert timeline.json()["rows"][0]["shot_id"] == "S001"

    review = client.get(f"/api/projects/{project_id}/review")
    assert review.status_code == 200
    assert review.json()["rows"][0]["beat_id"] == "B0001"

    preview = client.get(f"/api/projects/{project_id}/preview", params={"path": str(project_root / "reports" / "notes.md")})
    assert preview.status_code == 200
    assert "world" in preview.json()["content"]
