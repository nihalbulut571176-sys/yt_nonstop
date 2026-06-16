---
name: deployment-devops
description: Plan local deployment and operational packaging for the yt_nonstop web app. Use when defining local run modes, environment setup, packaging, process management, and future deployment paths beyond the current single-machine model.
---

# Deployment DevOps

## Repo Context

- Current deployment mode is local-machine only
- Backend runs via `yt-nonstop studio`
- Frontend can run through Vite dev server or backend-served build assets

## Workflow

1. Document the current local run path first.
2. Define reproducible setup for Python, Node, and required environment variables.
3. Separate development, operator-local, and future hosted deployment concerns.
4. Decide what should be packaged versus what should remain local workspace state.
5. Provide process-management guidance for running the studio reliably on a workstation.
6. Record future blockers for hosted or multi-user deployment.

## Inputs

- Current run commands
- Python and Node package setup
- Environment dependencies
- Target operator environment

## Outputs

- Runbook or deployment guidance
- Environment setup checklist
- Packaging recommendation
- Future deployment constraints

## Checklist

- Verify the local setup is reproducible
- Verify secrets and workspace paths are configurable
- Verify operator startup and shutdown are simple
- Verify generated assets stay outside deploy artifacts
- Verify future hosted deployment blockers are explicit
