# Web Studio

## Purpose

The first web studio is a local internal operator tool that wraps the existing `yt-nonstop` CLI.

It does not replace the pipeline. It launches the same commands we already trust, then reads the generated artifacts back into a browser UI.

## Scope In V1

The v1 studio ships with four operator screens:

- `Projects`
- `Pipeline`
- `Review`
- `Assets`

It is intentionally:

- single-operator
- local-machine only
- workspace-root aware
- built around the existing `C:\Users\MIKE\Documents\Codex\YT_visual` project-folder convention

## Backend

Backend source lives in:

```text
src/yt_nonstop/webapi/
```

Key responsibilities:

- discover projects under the workspace root
- normalize repo-native and artifact-style folders into one project model
- run `yt-nonstop` subprocess jobs in the background
- persist lightweight job metadata under `.runtime/webstudio/`
- expose status, review, timeline, artifact, and log endpoints

Primary endpoints:

- `GET /api/projects`
- `GET /api/projects/{id}`
- `GET /api/projects/{id}/status`
- `GET /api/projects/{id}/artifacts`
- `GET /api/projects/{id}/timeline`
- `GET /api/projects/{id}/review`
- `POST /api/projects/{id}/validate`
- `POST /api/projects/{id}/run`
- `POST /api/projects/{id}/review/apply`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/logs`

## Frontend

Frontend source lives in:

```text
web/app/
```

It is a React SPA intended for local operator use. The UI keeps persistent project context, current stage visibility, quick access to logs, and direct browsing of generated artifacts.

## Running It

Install Python dependencies for the repo, then run:

```bash
yt-nonstop studio --reload
```

That starts the FastAPI backend on `127.0.0.1:8787`.

For frontend development:

```bash
cd web/app
npm install
npm run dev
```

The Vite dev server proxies `/api` calls to the backend.

For a built local bundle:

```bash
cd web/app
npm run build
```

If `web/app/dist/` exists, the FastAPI app serves the built studio directly.

## Configuration

Environment variables:

- `YT_NONSTOP_REPO_ROOT`
- `YT_NONSTOP_WORKSPACE_ROOT`
- `YT_NONSTOP_WEB_RUNTIME_DIR`
- `YT_NONSTOP_ALLOWED_PROJECT_ROOTS`
- `YT_NONSTOP_WEB_POLL_SECONDS`

Defaults assume:

- repo root: `C:\Users\MIKE\Documents\Codex\YT`
- workspace root: `C:\Users\MIKE\Documents\Codex\YT_visual`

## Current Limits

- no auth
- no multi-user support
- no project creation wizard
- no direct prompt editing
- no arbitrary filesystem browsing outside allowed project roots
- no queue/worker infra beyond local subprocess execution
