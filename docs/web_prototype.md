# Web Prototype

## Purpose

The next web phase should live inside `yt_nonstop`, not in a separate repository.

The goal is to wrap the existing workflow, not replace it.

## Current Prototype Sources

The current lightweight prototype sources live under:

```text
web/remotion-fastgen-first120/
```

Included there:
- `package.json`
- `remotion/entry.jsx`
- `remotion/index.jsx`
- `remotion/fastgenFirst120Data.js`
- compact notes and scene metadata from the first 120-second prototype

## What This Prototype Covers

It captures a first web-facing experiment for:
- Remotion composition structure
- scene-driven first-120-seconds storytelling
- layered motion-graphics treatment over generated visuals
- a practical bridge between pipeline outputs and a browser-renderable presentation layer

## What It Does Not Yet Cover

- full project ingestion UI
- project/job management
- background task orchestration
- end-to-end operator workflow in a browser
- final production asset management

## Relationship To The Future Web App

The future web app should:
- reuse the same project-folder model
- wrap existing pipeline stages rather than fork them
- surface status for `input/work/images/output`
- eventually expose controls for planning, generation, QC, and render

The current prototype is a source artifact and reference implementation, not the finished web product.

## Current Status

That next step now exists as the first local studio implementation:

- backend: `src/yt_nonstop/webapi/`
- frontend: `web/app/`

The Remotion prototype remains valuable as a motion/reference source, but it is no longer the only web-facing artifact in the repo.
