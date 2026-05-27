# FastGen-Only Battle Plan

## Goal

Bring the project to a reliable `audio -> final mp4` backbone as fast as possible, without overbuilding creative or publishing layers that do not materially unblock final video production.

## Rule of focus

We do not optimize for perfect prompts, thumbnails, or metadata first.  
We optimize for a repeatable project-local pipeline that:

1. accepts a new audio file as a new project;
2. creates and validates intermediate artifacts;
3. generates scene-linked still images;
4. normalizes them;
5. builds a slideshow timeline;
6. renders a final video with the original audio.

## What we intentionally defer

- advanced creative automation
- semantic scene scoring
- A/B thumbnail automation
- title/description scoring
- subtitles burn-in
- intro/outro/music/watermark layers
- dashboard/UI
- deep prompt-quality heuristics
- complex selective regenerate flows

## P0 backbone

### 1. Unified runner

Deliver `scripts/run_fastgen_only_project.py` with:

- `--project-json`
- `--from`
- `--to`
- `--resume`
- `--dry-run`

### 2. Minimal validation

Deliver `scripts/validate_project.py` with stage checks for:

- transcription
- scene plan
- prompt package
- prompt export
- images
- normalized images
- timeline
- render

### 3. Project-aware FastGen generation

Deliver project-scoped image generation so the pipeline can read:

- `projects/<id>/prompts/fastgen_prompts_generator_ready.md`

and write:

- `projects/<id>/images/fastgen_run/run_manifest.json`
- `projects/<id>/images/fastgen_run/images/*.png`

with scene-aware manifest linkage.

### 4. Project-aware normalization

Deliver normalization into:

- `projects/<id>/images/normalized/*.png`

and update scene assets for timeline/render.

### 5. Timeline and render continuity

Keep slideshow assembly project-local and verify that final duration stays aligned to audio.

## Execution order

1. add shared project pipeline utilities
2. add battle-plan document
3. add `validate_project.py`
4. add project-aware FastGen adapter
5. add project-aware normalization adapter
6. add unified runner
7. connect stage statuses and logs
8. smoke-test on a temporary project
9. refresh workflow docs if needed

## Done criteria for P0

The backbone is considered done when:

- one command can progress an existing project from transcription through render;
- every stage writes machine-readable output into the project folder;
- validation can fail fast with clear messages;
- generated images are traceable back to `scene_id`;
- render uses project-local normalized images;
- final video is produced without manual path editing.

## Follow-up after P0

Only after the backbone is stable do we move to:

- LLM-authored prompt layer
- selective regeneration
- thumbnail generation execution
- publishing draft automation refinement
- richer QC and creative guidance

## New prompt-authoring rule

Prompt writing should no longer be treated as a rule-based Python job.

New split:

- `Python` prepares scene timing, context packs, manifests, validation, and exports
- `LLM` writes the final visual prompts

Target flow:

1. `build_project_prompt_package.py` creates structure
2. Python builds `scene_context_pack.json`
3. the language model writes `llm_prompt_drafts.json`
4. Python validates and exports FastGen-ready prompts
