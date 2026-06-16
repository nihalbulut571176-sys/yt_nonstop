---
name: observability-debugging
description: Improve observability and debugging for yt_nonstop automation and web runs. Use when designing logs, job traces, runtime diagnostics, operator debug views, and failure triage for local pipeline execution.
---

# Observability Debugging

## Repo Context

- Jobs already capture stdout/stderr to runtime logs
- Operators need to debug pipeline failures without reading many raw files
- The workflow includes long-running generation and render tasks

## Workflow

1. Map where failures currently surface: CLI, runtime logs, project artifacts, review outputs.
2. Identify what operators need immediately versus what engineers need for deeper triage.
3. Design concise runtime status and richer drill-down logs.
4. Prefer structured job metadata over only raw text streams.
5. Link failures to actionable project context such as stage, command, project path, and next action.
6. Keep local debug tools lightweight and easy to clear.

## Inputs

- Current job store and logs
- Existing reports and artifacts
- Common operator failure cases
- Backend/frontend debug surfaces

## Outputs

- Observability plan
- Logging and diagnostics guidance
- Debug-view improvements
- Failure triage checklist

## Checklist

- Verify each job has enough context for triage
- Verify errors map back to project and stage
- Verify operators can distinguish blocker versus noise
- Verify logs stay local and manageable
- Verify cleanup/retention expectations are defined
