from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from yt_nonstop.webapi.artifacts import list_artifacts, load_review, load_timeline, preview_file
from yt_nonstop.webapi.config import WebConfig
from yt_nonstop.webapi.jobs import JobStore, build_cli_command
from yt_nonstop.webapi.models import ReviewApplyRequest, RunRequest, ValidateRequest
from yt_nonstop.webapi.project_discovery import discover_projects, get_project


def create_app() -> FastAPI:
    config = WebConfig.from_env()
    jobs = JobStore(config)
    app = FastAPI(title="yt_nonstop web studio", version="0.1.0")
    app.state.config = config
    app.state.jobs = jobs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def resolve_project(project_id: str):
        try:
            project = get_project(config, project_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Project not found")
        path = Path(project.path)
        if not config.project_allowed(path):
            raise HTTPException(status_code=403, detail="Project path is outside allowed roots")
        return project, path

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/projects")
    def projects():
        return [item.model_dump() for item in discover_projects(config)]

    @app.get("/api/projects/{project_id}")
    def project_details(project_id: str):
        project, _path = resolve_project(project_id)
        return project.model_dump()

    @app.get("/api/projects/{project_id}/status")
    def project_status(project_id: str):
        project, _path = resolve_project(project_id)
        return project.dashboard or {"status": project.status, "support": project.support}

    @app.get("/api/projects/{project_id}/artifacts")
    def project_artifacts(project_id: str):
        _project, path = resolve_project(project_id)
        return [item.model_dump() for item in list_artifacts(path)]

    @app.get("/api/projects/{project_id}/timeline")
    def project_timeline(project_id: str):
        project, path = resolve_project(project_id)
        payload = load_timeline(project_id, path, Path(project.project_json_path) if project.project_json_path else None)
        return payload.model_dump()

    @app.get("/api/projects/{project_id}/review")
    def project_review(project_id: str):
        project, path = resolve_project(project_id)
        payload = load_review(project_id, path, Path(project.project_json_path) if project.project_json_path else None)
        return payload.model_dump()

    @app.post("/api/projects/{project_id}/validate")
    def project_validate(project_id: str, request: ValidateRequest):
        project, _path = resolve_project(project_id)
        if not project.project_json_path:
            raise HTTPException(status_code=400, detail="Limited-support project has no project.json for validate")
        result = jobs.start_job(
            project_id=project_id,
            command=build_cli_command(project_json_path=project.project_json_path, action="validate", stage=request.stage),
            read_only=True,
        )
        status_code = 202 if result.accepted else 409
        return {"accepted": result.accepted, "reason": result.reason, "job": result.job.model_dump(), "status_code": status_code}

    @app.post("/api/projects/{project_id}/run")
    def project_run(project_id: str, request: RunRequest):
        project, _path = resolve_project(project_id)
        if not project.project_json_path:
            raise HTTPException(status_code=400, detail="Limited-support project has no project.json for run")
        result = jobs.start_job(
            project_id=project_id,
            command=build_cli_command(
                project_json_path=project.project_json_path,
                action="run",
                from_stage=request.from_stage,
                to_stage=request.to_stage,
                profile=request.profile,
                limit_frames=request.limit_frames,
                real_generation=request.real_generation,
                concurrency=request.concurrency,
                resume=request.resume,
                retry_failed_only=request.retry_failed_only,
                render_dry_run=request.render_dry_run,
                dry_run=request.dry_run,
            ),
            read_only=False,
        )
        status_code = 202 if result.accepted else 409
        return {"accepted": result.accepted, "reason": result.reason, "job": result.job.model_dump(), "status_code": status_code}

    @app.post("/api/projects/{project_id}/review/apply")
    def project_review_apply(project_id: str, request: ReviewApplyRequest):
        project, _path = resolve_project(project_id)
        if not project.project_json_path:
            raise HTTPException(status_code=400, detail="Limited-support project has no project.json for review")
        result = jobs.start_job(
            project_id=project_id,
            command=build_cli_command(project_json_path=project.project_json_path, action="review", dry_run=request.dry_run),
            read_only=False,
        )
        status_code = 202 if result.accepted else 409
        return {"accepted": result.accepted, "reason": result.reason, "job": result.job.model_dump(), "status_code": status_code}

    @app.get("/api/jobs")
    def list_jobs():
        return [item.model_dump() for item in jobs.list_jobs()]

    @app.get("/api/jobs/{job_id}")
    def get_job_endpoint(job_id: str):
        try:
            return jobs.get_job(job_id).model_dump()
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")

    @app.get("/api/jobs/{job_id}/logs")
    def get_job_logs(job_id: str, tail: int = Query(default=200, ge=1, le=1000)):
        try:
            return {"job_id": job_id, "lines": jobs.read_logs(job_id, tail=tail)}
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")

    @app.get("/api/projects/{project_id}/preview")
    def preview(project_id: str, path: str):
        _project, project_path = resolve_project(project_id)
        candidate = Path(path).resolve(strict=False)
        try:
            candidate.relative_to(project_path.resolve(strict=False))
        except ValueError:
            raise HTTPException(status_code=403, detail="Preview path is outside the project")
        if not candidate.exists() or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Preview file not found")
        payload = preview_file(candidate)
        return payload.model_dump()

    @app.get("/api/projects/{project_id}/media")
    def media(project_id: str, path: str):
        _project, project_path = resolve_project(project_id)
        candidate = Path(path).resolve(strict=False)
        try:
            candidate.relative_to(project_path.resolve(strict=False))
        except ValueError:
            raise HTTPException(status_code=403, detail="Media path is outside the project")
        if not candidate.exists() or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Media file not found")
        return FileResponse(candidate)

    dist_dir = config.repo_root / "web" / "app" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="studio")

    return app
