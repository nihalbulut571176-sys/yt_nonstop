---
name: testing-quality-gate
description: Define quality gates for yt_nonstop web and automation changes. Use when planning backend tests, frontend tests, smoke scenarios, regression coverage, and release criteria for operator-facing features.
---

# Testing Quality Gate

## Repo Context

- Backend tests run through `pytest`
- Frontend tests run through `vitest`
- The app mixes API, local files, background jobs, and browser-facing operator flows

## Workflow

1. Identify the highest-risk behavior change first.
2. Add contract tests around backend state, jobs, and filesystem boundaries.
3. Add frontend tests for rendering, key actions, and disabled-state behavior.
4. Keep at least one realistic smoke path that exercises the studio end to end.
5. Distinguish fast publish gates from deeper manual QA.
6. Capture known warnings and why they are acceptable or not.

## Inputs

- Feature change list
- Current backend and frontend contracts
- Known regression risks
- CI or local verification expectations

## Outputs

- Test matrix
- Required automated checks
- Manual smoke scenarios
- Release gate recommendation

## Checklist

- Verify critical write actions have backend coverage
- Verify frontend action flows are tested at smoke level
- Verify limited-support behavior is covered
- Verify build/test commands are documented
- Verify known warnings are classified, not ignored blindly
