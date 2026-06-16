---
name: automation-workflow-designer
description: Model the narrated-video automation workflow inside yt_nonstop. Use when defining stages, state transitions, resumability, operator actions, and how project runs move from input to prompts, generation, review, and render.
---

# Automation Workflow Designer

## Repo Context

- Real workflow is documented in `docs/production_workflow.md`
- Projects live outside git in `YT_visual`
- The web app must orchestrate existing pipeline stages, not fork them

## Workflow

1. Map the real stage sequence and operator checkpoints.
2. Identify which actions are read-only and which actions mutate project state.
3. Define resumable transitions, retry paths, and failure handling.
4. Mark blockers that should stop downstream stages versus warnings that should remain visible but non-blocking.
5. Keep the workflow monotonic and explicit for long-running jobs.
6. Ensure every web action corresponds to a real CLI command or artifact convention.

## Inputs

- Pipeline stage definitions
- Current CLI commands
- Project status outputs and reports
- Operator pain points around timing, prompts, generation, QC, and render

## Outputs

- Workflow diagram or stage map
- Operator action matrix
- Retry/resume rules
- Blocking versus warning semantics

## Checklist

- Verify every action maps back to a real pipeline capability
- Verify resumability is preserved
- Verify write actions are explicitly constrained
- Verify review and render dependencies are spelled out
- Verify failure and recovery paths are operator-readable
