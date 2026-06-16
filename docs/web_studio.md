# Web Studio MVP

## Purpose

The web studio is a local-first product shell around the existing `yt-nonstop` CLI and project-folder workflow.

The CLI and project artifacts remain the execution truth. The web app owns operator-facing state such as login sessions, project registry metadata, run history, review decisions, cached asset indexes, and non-secret settings.

## Source Layout

```text
src/yt_nonstop/webapi/   FastAPI backend, app-state DB, run orchestration
web/app/                 React studio frontend
```

The default project workspace remains:

```text
C:\Users\MIKE\Documents\Codex\YT_visual
```

## MVP Pages

- `Login`: local operator sign-in and session restore.
- `Projects`: discovered local projects plus support/status summaries.
- `Project Overview`: lifecycle, blockers, next action, recent runs, latest outputs.
- `Pipeline`: validate/resume/retry/render dry-run controls backed by CLI subprocess runs.
- `Review`: review artifact rows plus persisted operator decisions.
- `Assets`: grouped images, final images, videos, prompts, timelines, and reports with bounded previews.
- `Runs / History`: project-scoped and global runs with status, command, logs, and events.
- `Settings`: operator preferences, workspace metadata, FastGen provider metadata, and secret presence flags.

## Backend Model

The backend is a typed local product API:

- Auth/session endpoints live under `/api/auth/*`.
- Workspace and project state live under `/api/workspace/*` and `/api/projects/*`.
- Long-running operator actions are represented as runs under `/api/runs/*`.
- Review decisions are persisted in SQLite but source review artifacts remain in the project folder.
- Assets are indexed from project folders and preview/media reads are restricted to allowed project roots.
- Settings persist non-secret preferences in SQLite; secrets stay in env/local secret storage.

Important rule: browser write actions are bounded to project intake/bootstrap, launching CLI-backed runs, saving review decisions, and saving typed settings.

## Project Intake Flow

The intended operator path for a new video is:

1. Open `New Project`.
2. Choose `Upload source files`.
3. Add:
   - source SRT
   - source audio
   - raw narration text
   - optional style/setup notes
4. Click `Create project and open overview`.
5. Review project state on `Overview`.
6. Start `Validate` or `Resume` from `Pipeline`.

Uploaded files are staged under:

```text
.runtime/webstudio/uploads/
```

The backend then calls the same repo-native bootstrap logic used by the path-based API. The final project folder is created under `YT_visual`, and project artifacts remain there.

The current repo-native intake still requires an SRT timing source. If the operator only has MP3 + script text, the next product step is a draft intake mode that runs transcription before bootstrap.

## App-State Database

SQLite is stored under the configured runtime directory, normally:

```text
.runtime/webstudio/studio.sqlite3
```

The DB is for web concerns only:

- users and sessions
- projects and snapshots
- runs and run events
- review items and decisions
- asset indexes
- provider metadata
- user preferences
- audit events

Large media, prompts, reports, timelines, renders, and generated files stay in project folders, not in SQLite.

## Running Locally

```bash
yt-nonstop studio --host 127.0.0.1 --port 8787 --reload
```

Open:

```text
http://127.0.0.1:8787
```

Frontend development:

```bash
cd web/app
npm install
npm run dev
```

Production frontend bundle:

```bash
cd web/app
npm run build
```

If `web/app/dist/` exists, FastAPI serves the built studio.

## Configuration

Core environment variables:

- `YT_NONSTOP_REPO_ROOT`
- `YT_NONSTOP_WORKSPACE_ROOT`
- `YT_NONSTOP_WEB_RUNTIME_DIR`
- `YT_NONSTOP_ALLOWED_PROJECT_ROOTS`
- `YT_NONSTOP_WEB_POLL_SECONDS`
- `YT_NONSTOP_STUDIO_USERNAME`
- `YT_NONSTOP_STUDIO_PASSWORD`
- `YT_NONSTOP_STUDIO_SESSION_TTL_HOURS`
- `YT_NONSTOP_WEB_DEFAULT_PROFILE`
- `YT_NONSTOP_WEB_DEFAULT_CONCURRENCY`

FastGen metadata:

- `FASTGEN_API_URL`
- `FASTGEN_MODEL`
- `FASTGEN_API_KEY`

`FASTGEN_API_KEY` is exposed to the UI only as a configured/missing flag. The value is never returned by `/api/settings`.

## MVP Smoke Checklist

Use this checklist before treating a branch as a usable local studio build:

1. Start the app with `yt-nonstop studio --reload`.
2. Sign in with the configured local operator account.
3. Open `Projects` and confirm local projects are discovered under `YT_visual`.
4. Create/bootstrap a small project from `/projects/new` by uploading SRT, audio, raw text, and optional style notes.
5. Open the project overview and confirm lifecycle, blockers, next action, and recent runs render.
6. Launch `validate` or `resume` from `Pipeline`.
7. Inspect active run status, logs, and project/global run history.
8. Open `Review`, save a decision, refresh, and confirm it persists.
9. Open `Assets`, preview a text artifact, image, and video if available.
10. Open `Settings` and confirm FastGen secret is shown only as presence metadata.

## Publish Gate

Fast local gate:

```bash
python -m pytest tests\test_webapi.py
cd web/app
npm test
npm run build
yt-nonstop studio --help
```

Known acceptable warnings:

- Starlette/httpx deprecation warning from the FastAPI test client.
- React Router v7 future-flag warnings in Vitest.

Any auth, filesystem boundary, run conflict, review persistence, asset preview, or secret-redaction regression should block publication.

## Current Limits

- Local-first single-operator deployment only.
- Role model exists, but full multi-user collaboration is not implemented.
- No arbitrary project config editing in the browser.
- No prompt editing UI.
- No hosted worker queue or remote execution.
- Remotion remains reference/prototype material, not a first-class studio module yet.
