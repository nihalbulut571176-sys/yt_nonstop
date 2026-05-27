# FastGen-Only Workflow Guide

## What This Workflow Is

This project is a `fastgen_only` YouTube production workflow.

It turns:

- source text
- recorded or generated voiceover audio

into:

- a structured scene plan tied to real audio timing
- an LLM-authored visual prompt package
- FastGen-ready still-image prompts
- a slideshow-style final video
- a publishing package with title, description, and thumbnail preparation

This workflow does **not** use VNonStop animation.

## Core Rule

The source of truth is a combination of **real audio timing** and **cleaned wording**.

Production formula:

- `Whisper SRT` = source of timing
- `source script` = source of meaning
- `cleaned timed transcript` = source for scene planning
- `Python` = structure, timing, files, validation, export
- `LLM` = visual direction, project visual bible, scene prompts

We do not decide image count from sentence count alone.

## Project Structure

Every new audio file becomes a new isolated project:

- `projects/<project_id>/`

Each project contains:

- `project.json`
- `input/`
- `audio/`
- `transcript/`
- `scene_plan/`
- `prompts/`
- `images/`
- `renders/`
- `publishing/`
- `logs/`

### Folder Roles

`input/`

- raw text
- rewritten script
- approved script

`audio/`

- copied or downloaded voiceover file for this project

`transcript/`

- `.srt`
- `.segments.json`
- transcription metadata
- cleaned transcript artifacts

`scene_plan/`

- sentence blocks
- long segment report
- canonical `scene_plan.json`

`prompts/`

- `prompt_package.json`
- `scene_context_pack.json`
- `visual_bible.json`
- `visual_bible_review.md`
- `llm_prompt_drafts.json`
- `llm_prompt_drafts_v2_in_progress.json`
- `llm_prompt_rewrite_status.json`
- `full_rewrite_batch_plan.json`
- `prompt_review.md`
- `fastgen_prompts_generator_ready.md`

`images/`

- FastGen run folder
- normalized images for final montage

`renders/`

- slideshow timeline
- ffconcat
- final rendered video

`publishing/`

- title drafts
- description drafts
- thumbnail brief
- thumbnail prompt candidates
- approved publishing assets

`logs/`

- pipeline logs
- event logs

## Main Files

### Workflow Docs

- [pipeline_anchor_plan.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/pipeline_anchor_plan.md)
- [pipeline_data_models.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/pipeline_data_models.md)
- [fastgen_only_battle_plan.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/fastgen_only_battle_plan.md)
- [project.template.json](C:/Users/MIKE/Documents/Codex/YT/deliverables/project.template.json)
- [workflow_operating_instructions_fastgen_only.json](C:/Users/MIKE/Documents/Codex/YT/deliverables/workflow_operating_instructions_fastgen_only.json)
- [llm_prompt_authoring_design.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/llm_prompt_authoring_design.md)
- [visual_bible_master_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/visual_bible_master_prompt.md)
- [codex_full_rewrite_operator_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/codex_full_rewrite_operator_prompt.md)
- [visual_shot_plan_implementation_spec.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/visual_shot_plan_implementation_spec.md)
- [visual_shot_plan_operator_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/visual_shot_plan_operator_prompt.md)
- [shot_prompt_package_operator_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/shot_prompt_package_operator_prompt.md)

### Main Scripts

- [bootstrap_fastgen_only_project.py](C:/Users/MIKE/Documents/Codex/YT/scripts/bootstrap_fastgen_only_project.py)
- [transcribe_faster_whisper.py](C:/Users/MIKE/Documents/Codex/YT/scripts/transcribe_faster_whisper.py)
- [cleanup_transcript_from_source.py](C:/Users/MIKE/Documents/Codex/YT/scripts/cleanup_transcript_from_source.py)
- [build_project_scene_plan.py](C:/Users/MIKE/Documents/Codex/YT/scripts/build_project_scene_plan.py)
- [prepare_project_publishing_package.py](C:/Users/MIKE/Documents/Codex/YT/scripts/prepare_project_publishing_package.py)
- [build_project_prompt_package.py](C:/Users/MIKE/Documents/Codex/YT/scripts/build_project_prompt_package.py)
- [build_scene_context_pack.py](C:/Users/MIKE/Documents/Codex/YT/scripts/build_scene_context_pack.py)
- [build_visual_shot_plan.py](C:/Users/MIKE/Documents/Codex/YT/scripts/build_visual_shot_plan.py)
- [build_shot_prompt_package.py](C:/Users/MIKE/Documents/Codex/YT/scripts/build_shot_prompt_package.py)
- [expand_shot_prompts_to_scene_drafts.py](C:/Users/MIKE/Documents/Codex/YT/scripts/expand_shot_prompts_to_scene_drafts.py)
- [apply_llm_prompt_drafts.py](C:/Users/MIKE/Documents/Codex/YT/scripts/apply_llm_prompt_drafts.py)
- [export_project_fastgen_prompts.py](C:/Users/MIKE/Documents/Codex/YT/scripts/export_project_fastgen_prompts.py)
- [run_project_fastgen_generation.py](C:/Users/MIKE/Documents/Codex/YT/scripts/run_project_fastgen_generation.py)
- [normalize_project_images.py](C:/Users/MIKE/Documents/Codex/YT/scripts/normalize_project_images.py)
- [build_project_slideshow_timeline.py](C:/Users/MIKE/Documents/Codex/YT/scripts/build_project_slideshow_timeline.py)
- [render_project_slideshow_video.ps1](C:/Users/MIKE/Documents/Codex/YT/scripts/render_project_slideshow_video.ps1)
- [validate_project.py](C:/Users/MIKE/Documents/Codex/YT/scripts/validate_project.py)
- [run_fastgen_only_project.py](C:/Users/MIKE/Documents/Codex/YT/scripts/run_fastgen_only_project.py)

## Fastest Reliable Path

If the goal is to reach a final video quickly, the recommended path is:

1. bootstrap project from audio
2. transcribe
3. cleanup transcript from source text when available
4. build scene plan
5. build prompt package
6. build neutral scene context pack
7. let the LLM write `visual_bible.json`
8. let the LLM write `llm_prompt_drafts.json`
9. apply drafts through Python into the prompt package
10. prepare publishing package
11. export prompts
12. generate images
13. normalize images
14. build timeline
15. render video

This path is intentionally narrower than the larger long-term vision. It focuses on the shortest reliable route from audio to final video.

### Optional Shot-Planning Layer

For future long-form projects, an additional planning layer can sit between `visual_bible.json` and `llm_prompt_drafts.json`:

```text
scene_context_pack.json
-> visual_bible.json
-> visual_shot_plan.json
-> shot_prompt_package.json
-> expand_shot_prompts_to_scene_drafts.py
-> llm_prompt_drafts.json
```

This is a phase-1 compatibility layer for reducing unnecessary prompt uniqueness without changing the current render pipeline yet.

The next evaluation target is not `fast` render reuse yet.
The next target is `standard`-mode grouping quality:

- good `hero/supporting/continuity/bridge/reuse` decisions
- strong `visual_anchor` coverage
- fewer unnecessary unique prompts
- no off-topic drift caused by abstract grouping

## Unified Runner And Validation

Backbone scripts:

- `scripts/run_fastgen_only_project.py`
- `scripts/validate_project.py`

Runner example:

```powershell
python scripts/run_fastgen_only_project.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\my_project_001\project.json" `
  --from cleanup_transcript_from_source `
  --to render
```

Resume example:

```powershell
python scripts/run_fastgen_only_project.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\my_project_001\project.json" `
  --resume
```

Validation example:

```powershell
python scripts/validate_project.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\my_project_001\project.json" `
  --stage all
```

## Stage-By-Stage Workflow

## Stage 1: Create a New Project From Audio

Input:

- local audio path or audio URL
- optional raw text path
- chosen `project_id`

Script:

- `scripts/bootstrap_fastgen_only_project.py`

What it does:

- creates `projects/<project_id>/`
- copies or downloads audio into project `audio/`
- creates `project.json`
- creates publishing scaffold files
- optionally starts transcription immediately

## Stage 2: Transcription

Input:

- project audio

Script:

- `scripts/transcribe_faster_whisper.py`

What it produces:

- `.srt`
- `.segments.json`
- `.meta.json`

Default language is `auto`. A project can still force a specific language when needed.

## Stage 3: Transcript Cleanup And Alignment

Input:

- Whisper `srt`
- Whisper segment timings
- optional source script

Script:

- `scripts/cleanup_transcript_from_source.py`

What it does:

- keeps timing from Whisper
- takes wording from source script when available
- writes:
  - `transcript/cleaned.srt`
  - `transcript/cleaned_segments.json`
  - `transcript/cleaned_timed_transcript.md`
  - `transcript/cleanup_report.json`

## Stage 4: Build Scene Plan

Input:

- project `srt`

Script:

- `scripts/build_project_scene_plan.py`

What it does:

- parses `SRT`
- merges subtitle lines into sentence blocks
- splits long segments into multiple scenes
- creates canonical `scene_plan.json`
- creates `sentence_blocks.json`
- creates `long_segment_report.json`

Important rule:

- no still scene should hold longer than 5 seconds

## Stage 5: Build Prompt Package

Input:

- canonical `scene_plan.json`

Script:

- `scripts/build_project_prompt_package.py`

What it creates:

- `prompts/prompt_package.json`
- `prompts/prompt_review.md`

Purpose:

- create a project-local prompt layer for every scene
- keep a machine-readable base package before LLM authoring

## Stage 6: Build Neutral Scene Context Pack

Input:

- `prompts/prompt_package.json`
- `scene_plan/scene_plan.json`

Script:

- `scripts/build_scene_context_pack.py`

What it creates:

- `prompts/scene_context_pack.json`

Purpose:

- give the LLM a structured source of truth for:
  - scene ids
  - timings
  - local narration
  - neighboring narration
  - style summary
  - language settings
  - story arc context
  - neutral role hints

Important rule:

- `scene_context_pack.json` should stay neutral
- Python should not decide documentary meaning here

## Stage 7: LLM Visual Bible

Input:

- `prompts/scene_context_pack.json`
- full approved script when available
- [visual_bible_master_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/visual_bible_master_prompt.md)

What it creates:

- `prompts/visual_bible.json`
- optional `prompts/visual_bible_review.md`

Purpose:

- define the project-wide visual world before per-scene prompt writing
- let the LLM decide:
  - main subject
  - subject type
  - recurring motifs
  - continuity rules
  - forbidden mistakes
  - visual blocks

## Stage 8: LLM Prompt Authoring

Input:

- `prompts/scene_context_pack.json`
- `prompts/visual_bible.json`
- project master prompt

What it creates:

- `prompts/llm_prompt_drafts.json`

Purpose:

- let the language model act as visual director and prompt writer
- keep prompt writing out of rule-based Python
- author prompts in batches with neighboring context
- in autonomous rewrite mode, let Codex operate through [codex_full_rewrite_operator_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/codex_full_rewrite_operator_prompt.md)
- write both markdown and JSON review artifacts before merging a batch

## Stage 9: Apply LLM Prompt Drafts

Input:

- `prompts/llm_prompt_drafts.json`

Script:

- `scripts/apply_llm_prompt_drafts.py`

What it updates:

- `prompts/prompt_package.json`
- `scene_plan/scene_plan.json`
- `prompts/prompt_review.md`

Purpose:

- ingest LLM-authored drafts through Python
- validate required fields before export
- keep the pipeline resumable and machine-readable

## Stage 10: Prepare Publishing Package

Input:

- raw text if available
- rewritten or approved script if available
- scene plan excerpts

Script:

- `scripts/prepare_project_publishing_package.py`

What it creates or updates:

- `publishing/source_snapshot.md`
- `publishing/title_drafts.json`
- `publishing/description_drafts.json`
- `publishing/thumbnail_brief.md`
- `publishing/thumbnail_prompt_candidates.json`

## Stage 11: Export FastGen-Ready Prompt Blocks

Input:

- `prompts/prompt_package.json`

Script:

- `scripts/export_project_fastgen_prompts.py`

What it creates:

- `prompts/fastgen_prompts_generator_ready.md`

## Stage 12: Generate Images With FastGen

Input:

- `prompts/fastgen_prompts_generator_ready.md`

Scripts:

- `scripts/run_project_fastgen_generation.py`
- `scripts/fastgen_openai_v4_generate.py`

Expected output:

- `projects/<id>/images/fastgen_run/`

## Stage 13: Normalize Images

Input:

- generated FastGen stills

Script:

- `scripts/normalize_project_images.py`

Expected output:

- `projects/<id>/images/normalized/`

## Stage 14: Build Slideshow Timeline

Input:

- `scene_plan.json`
- normalized still images

Script:

- `scripts/build_project_slideshow_timeline.py`

What it creates:

- `renders/slideshow_timeline.json`
- `renders/timeline.ffconcat`

## Stage 15: Render Final Slideshow Video

Input:

- project ffconcat
- project audio

Script:

- `scripts/render_project_slideshow_video.ps1`

Output:

- `projects/<id>/renders/<project_id>.mp4`

## Publishing Assets

This workflow also prepares publication assets for YouTube.

### Title

- `publishing/title_drafts.json`
- `publishing/title_approved.txt`

### Description

- `publishing/description_drafts.json`
- `publishing/description_approved.md`

### Thumbnail

- `publishing/thumbnail_brief.md`
- `publishing/thumbnail_prompt_candidates.json`
- `publishing/thumbnail_prompt_approved.txt`
- `publishing/thumbnails/run_manifest.json`
- `publishing/thumbnails/candidates/`
- `publishing/thumbnails/approved.png`

## Current Working Reality

What is already real and working:

- per-audio-file project creation
- project-local folder structure
- project manifest creation
- transcription entry point
- scene-plan generation with max-5s splitting
- project-local prompt-package generation
- neutral scene-context-pack generation
- Python ingestion of LLM-authored drafts
- full rewrite batch planning and coverage tracking
- FastGen-ready prompt export
- slideshow timeline builder
- slideshow render entry point

What still remains to complete end-to-end:

- project-local `visual_bible.json` authoring pass as a standard operating step
- full project-aware autonomous LLM prompt pass for every scene in-run
- project-aware FastGen generation invocation refinement
- project-aware image normalization invocation refinement
- final one-command orchestration through a unified runner including explicit LLM stages

## Recommended Real-Work Sequence

For actual production right now:

1. create a project from audio
2. run or verify transcription
3. build the scene plan
4. build the prompt package
5. build the neutral scene context pack
6. create the visual bible
7. generate scene prompt drafts
8. apply drafts
9. export FastGen-ready prompt blocks
10. run FastGen image generation
11. normalize images
12. build slideshow timeline
13. render final video
14. finalize title, description, and thumbnail
