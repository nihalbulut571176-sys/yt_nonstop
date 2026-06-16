# yt_nonstop

`yt_nonstop` is the canonical repository for the current narrated-video workflow.

The repo contains:
- the production pipeline code
- FastGen and prompt-generation scripts
- validation and contract tests
- lightweight docs and sample fixtures
- the first in-repo web/Remotion prototype sources

The repo does not contain bulky local project outputs such as full image runs, final MP4 renders, MFA scratch data, or `node_modules`.

## Source Of Truth

- Canonical code repo: [nihalbulut571176-sys/yt_nonstop](https://github.com/nihalbulut571176-sys/yt_nonstop)
- Primary local repo path: `C:\Users\MIKE\Documents\Codex\YT`
- Local project workspace for large runs and artifacts: `C:\Users\MIKE\Documents\Codex\YT_visual`

The old `visual` working area is no longer the active source of truth for code.

## Key Docs

- [Repo Audit And Source Of Truth](docs/repo_audit_and_source_of_truth.md)
- [Project Workspace Convention](docs/project_workspace.md)
- [Production Workflow](docs/production_workflow.md)
- [Web Prototype](docs/web_prototype.md)
- [Technical FastGen Pilot](docs/technical_fastgen_pilot.md)

## Current Workflow

At a high level:
1. bootstrap or prepare a project folder
2. transcribe / clean text
3. build scene plan and frame briefs
4. export prompts and generation batches
5. run FastGen image generation
6. run QC / review
7. build timeline and render
8. optionally replace head segments with animated video clips and stitch back into the final render

## Project Layout

Repo-managed examples stay small under `sample_projects/`.

Real operator runs and heavy assets should stay outside git in local project folders, typically using:

```text
project/
  input/
  work/
  images/
  output/
```

## Web / Remotion Prototype

A lightweight prototype now lives under:

```text
web/remotion-fastgen-first120/
```

It is intentionally kept small and source-only. Generated assets and dependency folders stay outside git.
