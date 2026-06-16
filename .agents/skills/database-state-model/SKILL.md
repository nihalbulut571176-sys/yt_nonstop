---
name: database-state-model
description: Design state persistence for the yt_nonstop web app. Use when deciding what belongs in JSON, SQLite, runtime job stores, pipeline state tables, and how local project state should be represented without replacing project artifacts.
---

# Database State Model

## Repo Context

- Runtime state already exists in project artifacts and optional pipeline state stores
- Web layer currently persists lightweight job data under runtime files
- The application is local-first and single-operator for now

## Workflow

1. Separate canonical project artifacts from web runtime convenience state.
2. Keep the project folder as the truth for pipeline outputs.
3. Persist only the minimum extra web state needed for jobs, UI continuity, and operator quality-of-life.
4. Use SQLite when queryability or history matters; use JSON only when the state is trivial and append-only.
5. Design state with future migration to multi-project dashboards in mind, even if single-user remains the default.
6. Avoid duplicating large artifact payloads into the web database.

## Inputs

- Current artifact model
- Existing pipeline state helpers
- Job history needs
- Planned operator features

## Outputs

- State model recommendation
- Table or document boundaries
- Retention and cleanup rules
- Sync boundaries between runtime state and project artifacts

## Checklist

- Verify canonical project data is not duplicated unnecessarily
- Verify job history is queryable if product needs it
- Verify retention and cleanup are defined
- Verify future schema changes are feasible
- Verify local-first behavior remains simple to operate
