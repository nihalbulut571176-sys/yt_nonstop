# LLM and Python Responsibility Contract

This repository stays `SRT-first` and `scene-based`.

The canonical chain remains:

```text
cleaned.srt
-> scene_plan.json
-> prompt_package.json
-> scene_context_pack.json
-> visual_bible.json
-> llm_prompt_drafts.json
-> final_scene_plan.json
-> fastgen export
-> generation manifests
-> normalized stills
-> timeline
-> final video
```

## Source Of Truth

- Timing truth: `cleaned.srt` and then `scene_plan.json`
- Creative truth after planning: `visual_bible.json` and `llm_prompt_drafts.json`, but only inside existing `scene_id` slots
- Technical truth: project manifest, exported prompt files, generation manifests, image files, QA reports, render outputs

`LLM` is never the source of truth for filesystem state, runtime status, retries, or successful image creation.

## LLM Owns

- Story interpretation
- Visual worldbuilding
- Prompt writing for existing scenes
- Creative rewrite after semantic or prompt-quality failures
- Structured JSON artifacts only

Official LLM output contracts:

- `visual_bible.json`
- `llm_prompt_drafts.json`

Required scene-draft fields:

- `scene_id`
- `visual_goal`
- `final_prompt`

Recommended scene-draft fields:

- `shot_role`
- `primary_subject`
- `secondary_subjects`
- `what_is_in_frame`
- `camera`
- `composition`
- `lighting`
- `mood`
- `continuity_notes`
- `negative_prompt`
- event clarity fields

LLM output must be raw machine-readable JSON with no Markdown wrapper, commentary, or runtime claims.

## LLM Must Not Change

- `scene_id`
- `start`
- `end`
- `duration`
- scene order
- filesystem paths
- runtime statuses
- `job_id`
- image result metadata

Any draft that includes Python-owned timing, path, or runtime status fields is invalid and must be rejected by Python.

## Python Owns

- Context-pack assembly from canonical project files
- JSON ingestion and validation
- Scene-count and scene-id alignment checks
- Retry orchestration
- API calls
- File writes and path creation
- Manifest persistence
- Generation success/failure confirmation
- Technical QC and image readability checks

Python may request a semantic rewrite, but only Python can confirm:

- that a file exists
- that an image opens
- that export metadata matches
- that the run status is complete

## Hybrid Mode

The primary operating mode is hybrid JSON:

1. Python builds project context.
2. LLM writes artifact JSON.
3. Python validates and ingests that JSON.
4. Python exports generator-ready prompts and manages runtime.

An optional adapter interface may later automate LLM transport, but it must not bypass Python validation or write canonical scene outputs directly.
