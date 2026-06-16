---
name: product-web-app-architect
description: Design the product architecture for the yt_nonstop web application. Use when defining product boundaries, modules, user journeys, MVP versus later phases, and how the web studio should evolve around the existing CLI-driven automation workflow.
---

# Product Web App Architect

## Repo Context

- Canonical repo: `yt_nonstop`
- Current web stack: `FastAPI + React`
- Execution engine: existing `yt-nonstop` CLI and pipeline stages
- Local project workspace: `C:\Users\MIKE\Documents\Codex\YT_visual`

## Workflow

1. Read the current workflow and web docs before proposing product changes.
2. Identify the operator personas and the exact jobs they perform in `Projects`, `Pipeline`, `Review`, and `Assets`.
3. Separate source-of-truth concerns from convenience UI concerns.
4. Define the minimum product slices that wrap the CLI safely without replacing it.
5. Split the roadmap into MVP, production-hardening, and premium/productized layers.
6. Surface architectural risks, especially around long-running jobs, local files, and mixed project maturity.

## Inputs

- Current product goal or user request
- Existing docs under `docs/`
- Current backend/frontend capabilities
- Known workspace conventions and project-folder model

## Outputs

- Web app architecture recommendation
- Page map and user journeys
- MVP versus premium feature split
- Clear non-goals and risk notes

## Checklist

- Verify the proposal keeps CLI as the execution engine
- Verify the workspace-folder model remains explicit
- Verify every proposed page maps to a real operator task
- Verify MVP and later phases are clearly separated
- Verify risks and constraints are called out, not hidden
