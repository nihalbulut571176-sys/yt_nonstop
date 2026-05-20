# Workflow Profiles

## Purpose

This project supports two pipeline profiles inside one shared codebase and one shared project model.

The goal is to avoid maintaining duplicate folders or cloned repositories for workflows that share most of the same logic.

## Active Profiles

### `veononstop`

Config file:

- `configs/pipeline_profile_veononstop.json`

Use when:

- FastGen generates still images
- selected scenes are animated through VNonStop
- final render uses mixed cut logic: video when available, image otherwise

Key properties:

- animation enabled
- remote animation retries and backoff matter
- service instability must be tracked through append-only logs

### `fastgen_only`

Config file:

- `configs/pipeline_profile_fastgen_only.json`

Use when:

- FastGen generates still images
- no VNonStop stage is used
- final render is assembled entirely from still images and audio

Key properties:

- animation disabled
- no VNonStop logs or retries required
- simpler render path and faster operational turnaround

## Recommendation

Use:

- `main` as the stable baseline branch
- a dedicated feature branch when implementing larger workflow changes
- profile configs, not cloned folders, to express behavioral differences between workflows

This gives the project:

- one shared codebase
- one shared project model
- multiple execution modes
- less duplication and lower maintenance overhead
