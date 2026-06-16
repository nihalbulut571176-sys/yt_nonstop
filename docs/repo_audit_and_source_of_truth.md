# Repo Audit And Source Of Truth

## Current Baseline

- Canonical repository: `yt_nonstop`
- Local repo path: `C:\Users\MIKE\Documents\Codex\YT`
- Remote: `https://github.com/nihalbulut571176-sys/yt_nonstop.git`
- Active branch during this audit: `codex/python-llm-production-pipeline-v2`

At the time this note was added, the branch had local commits ahead of origin and additional unstaged / untracked code changes.

## What Lives Where

### Repo truth

The git repository is the source of truth for:
- pipeline code
- scripts
- tests
- contracts and validators
- operator docs
- lightweight sample fixtures
- lightweight web / Remotion prototype sources

### Local workspace truth

`C:\Users\MIKE\Documents\Codex\YT_visual` is the local artifact workspace for:
- full project folders
- generated PNG sets
- final MP4 outputs
- render temp folders
- MFA experiments
- ad hoc web prototype assets
- project-specific review and debug outputs

This workspace is intentionally not treated as the canonical code repository.

## Important Clarification

The older `visual` workflow area was useful for experiments and project runs, but the active codebase is now `yt_nonstop`.

If a future engineer needs the current implementation:
1. pull `yt_nonstop`
2. read the docs in `docs/`
3. treat `YT_visual` as local runtime/project storage rather than repo truth

## Classification Rules For Local-Only Materials

### Keep in repo

- code changes used by the real workflow
- tests covering those changes
- concise docs/specs
- small sample fixtures
- lightweight web prototype source files

### Keep local only

- generated images
- final videos
- render scratch outputs
- MFA scratch trees
- `node_modules`
- large per-project outputs

### Promote selectively

If a local artifact is needed in git, promote only the smallest durable representation:
- a small JSON fixture
- a compact README
- a short note explaining the operator workflow

Do not mirror entire project directories into the repo.
