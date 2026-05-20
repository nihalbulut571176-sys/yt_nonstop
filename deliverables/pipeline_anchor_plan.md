# YouTube Pipeline Anchor Plan

## Purpose

This document is the working anchor for the YouTube automation pipeline in this project.
Its role is to define:

- what the pipeline must do end-to-end
- what has already been validated
- what still needs to be implemented
- in what order we should implement it
- how we will decide that each stage is complete

This file should be treated as the project roadmap for pipeline automation and operational reliability.

## Core Goal

Build a repeatable pipeline that can take one user-provided source text and produce a final edited video with minimal manual intervention.

Target future workflow:

1. User sends source text.
2. Codex rewrites it into a strong voiceover-ready script.
3. User records or generates voiceover and places audio in the project.
4. Codex transcribes real audio with Whisper and generates SRT.
5. Codex derives a shot plan from real timing, splitting any overlong scene.
6. Codex generates visual prompts for all shots.
7. Codex sends prompts to FastGen and gathers ordered images.
8. Codex selects which shots should be animated.
9. Codex sends selected shots to VNonStop.
10. Codex assembles a mixed cut from stills and videos.
11. Codex prepares publishing assets: title, description, and thumbnail concepts.
12. Codex generates thumbnail candidates through FastGen.
13. Codex validates the result and delivers the final mp4 and publishing package.

## Non-Negotiable Operating Rules

These are confirmed rules and should not be broken unless explicitly revised.

- Real audio timing is the source of truth.
- SRT must be generated from the real audio before production prompts are finalized.
- Final image count must be derived from the shot plan, not from sentence count alone.
- No still frame should hold longer than 5 seconds.
- Character continuity must be preserved through selective reference usage.
- Timeline and manifest files are the authoritative basis for automation.
- Mixed cuts must use video when the shot is marked animated and the video exists; otherwise they must use the still image.
- Image normalization must happen before slideshow or mixed-cut assembly.
- Append-only logs must be preferred over overwrite-prone run snapshots.

## Current Confirmed Assets

The current project already contains important building blocks:

- transcription: `scripts/transcribe_faster_whisper.py`
- shot splitting: `scripts/build_max5s_shot_plan.py`
- timeline builders: `scripts/build_slideshow_timeline.py`, `scripts/build_stride_timeline.py`
- image generation: `scripts/fastgen_openai_v4_generate.py`
- image normalization: `scripts/normalize_images_for_video.py`
- video generation: `scripts/veononstop_image_to_video.py`
- mixed cut assembly: `scripts/render_partial_mixed_cut.py`
- operating memory: `deliverables/workflow_operating_instructions.json`

This means the main problem is now orchestration, state management, and reliability, not the absence of core functionality.

## Main Gaps To Close

These are the highest-value missing pieces in the current workflow.

### 1. No Single Project Manifest

The workflow spans multiple files and folders, but there is no single object that ties them together.

Need:

- a per-project manifest such as `project.json`
- stable references to raw text, final voice script, audio, transcript, shot plan, prompts, image outputs, video outputs, and final render
- stage-level statuses so the pipeline can resume cleanly

### 2. No Central Scene Model

The workflow has timeline and manifest files, but not yet one canonical scene-level structure.

Need:

- a central `scene_plan.json`
- one record per shot
- for each shot: timing, voice text, prompt, references, target asset, animation status, render source

### 3. No Unified Orchestrator

The project has scripts for individual tasks, but not yet one controller script.

Need:

- a top-level runner such as `scripts/run_pipeline.py`
- stage execution in correct dependency order
- resume behavior
- status tracking
- error reporting

### 4. No Formal QA Gate

The pipeline can produce assets, but there is not yet a dedicated validation phase before the final render.

Need:

- completeness checks
- timing checks
- missing file checks
- duplicate or broken asset checks
- summary report output

### 5. Animation Selection Is Still Campaign-Driven

Current stride timelines and special target runs are useful, but the long-term system should be policy-driven, not manually improvised.

Need:

- a formal animation-priority policy
- support for first-minute-heavy animation
- support for every-third-shot fallback
- support for content-priority animation tags

### 6. Text Rewrite Stage Is Not Yet Productized

The rewrite stage is conceptually defined, but it is not yet represented as a stable, versioned pipeline stage.

Need:

- a saved master prompt for script rewriting
- a consistent output format for voiceover scripts
- a place to record rewritten script versions

### 7. Publishing Layer Is Not Yet Formalized

The workflow currently focuses on script, visuals, animation, and render, but not yet on the publishing package that surrounds the video.

Need:

- a stable title-generation step
- a stable description-generation step
- a thumbnail-generation step
- a place to store approved versus draft publishing assets
- an approval flow for final publishing selections

## Delivery Phases

## Phase 0 - Stabilize the Specification

Goal:
Turn the current operational knowledge into an explicit implementation spec.

Tasks:

- confirm final terminology: project, scene, shot, campaign, cut, manifest
- define canonical file roles
- define which file is the source of truth at each stage
- define the exact state transitions for a project
- define success criteria for each pipeline stage

Deliverables:

- this anchor plan
- project data model draft
- scene data model draft
- stage/status model draft

Definition of done:

- we can explain the whole pipeline without ambiguity
- we can point to one file per responsibility

## Phase 1 - Define Canonical Data Structures

Goal:
Create the schemas that future automation will use.

Tasks:

- define `project.json`
- define `scene_plan.json`
- define `qc_report.json`
- define `animation_campaign.json` if needed
- define naming and folder conventions for per-project work

Suggested `project.json` responsibilities:

- project metadata
- raw text
- rewritten voice script
- audio file location
- transcript output locations
- scene plan location
- image generation run locations
- video generation run locations
- final cut locations
- pipeline stage statuses

Suggested `scene_plan.json` responsibilities:

- shot index
- start/end/duration
- source transcript text
- visual intent
- generation prompt
- references used
- still image path
- video path if generated
- should_animate flag
- render_source selected for final cut

Definition of done:

- schemas are agreed
- fields are sufficient to run the whole pipeline without guessing

## Phase 2 - Standardize Project Folder Layout

Goal:
Make each video project self-contained and reproducible.

Tasks:

- choose a `projects/<project_id>/` structure
- separate shared global assets from per-project outputs
- define where intermediate and final files live
- decide which legacy folders stay shared and which should become project-scoped

Suggested per-project structure:

- `projects/<id>/project.json`
- `projects/<id>/input/raw_text.md`
- `projects/<id>/input/voice_script.md`
- `projects/<id>/audio/`
- `projects/<id>/transcript/`
- `projects/<id>/scene_plan/`
- `projects/<id>/images/`
- `projects/<id>/video_runs/`
- `projects/<id>/renders/`
- `projects/<id>/publishing/`
- `projects/<id>/logs/`

Definition of done:

- a new project can be created without inventing folders on the fly
- outputs no longer depend on ad hoc path memory

## Phase 3 - Productize the Rewrite Stage

Goal:
Make the text-to-voice-script step stable and reusable.

Tasks:

- write and save the master prompt for rewriting source text
- define output expectations: hook, pacing, emotional turns, spoken clarity
- store rewritten script as a versioned asset
- define how manual revisions are recorded

Definition of done:

- the rewrite step has a repeatable input and output
- we can compare source text and voiceover-ready script cleanly

## Phase 3.5 - Productize Publishing Drafts

Goal:
Make title, description, and thumbnail generation part of the standard workflow instead of an afterthought.

Tasks:

- define the master prompt for title generation
- define the master prompt for description generation
- define the master prompt for thumbnail ideation
- define approval flow for drafts versus approved publishing assets
- define where thumbnail prompts, thumbnail candidates, and approved thumbnail files live

Definition of done:

- each project has a reproducible publishing package workflow
- title, description, and thumbnail drafts can be generated and reviewed consistently

## Phase 4 - Transcription and Timing Automation

Goal:
Formalize the audio-to-SRT stage as a reliable pipeline step.

Tasks:

- define accepted audio input formats
- define Whisper model/runtime defaults
- define transcript output files
- standardize output naming
- include transcript metadata in project state

Definition of done:

- any accepted audio file can produce standardized transcript outputs
- downstream stages can rely on stable transcript paths

## Phase 5 - Scene Planning and Max-5s Splitting

Goal:
Generate a production-safe scene plan from real audio timing.

Tasks:

- formalize the long-segment detection step
- formalize splitting logic for scenes over 5 seconds
- decide how sub-shots inherit context from their parent sentence
- generate the canonical `scene_plan.json`
- ensure continuity prompts for split scenes

Definition of done:

- no scene exceeds the allowed hold duration unless explicitly overridden
- final shot count is known before image generation begins

## Phase 6 - Prompt Generation System

Goal:
Generate strong, consistent, production-ready prompts from the scene plan.

Tasks:

- define prompt templates
- define how references are selected
- define no-reference behavior
- define continuity suffixes for split scenes
- define formatting rules required by FastGen

Definition of done:

- every scene has a valid generation prompt
- references are selective and intentional
- prompt formatting is compatible with the generator

## Phase 7 - FastGen Orchestration

Goal:
Turn prompts into a complete, ordered image set with reliable resume behavior.

Tasks:

- connect prompts to the canonical scene plan
- produce ordered image targets
- store request metadata and output paths
- support resume and partial reruns
- normalize all generated images for editing use

Definition of done:

- every planned shot has an image or a clear failure record
- image ordering matches scene order
- normalized assets are ready for assembly or animation

## Phase 8 - Animation Target Policy

Goal:
Replace ad hoc animation campaigns with a clear decision policy.

Tasks:

- formalize "animate first minute fully"
- formalize "animate every third shot afterwards"
- add optional priority boosts for human subjects, movement, transitions, maps, interfaces, and key emotional beats
- allow manual override flags per shot
- generate campaign manifests automatically

Definition of done:

- animation selection can be reproduced from rules
- special campaigns no longer require manual guesswork

## Phase 9 - VNonStop Orchestration

Goal:
Run remote video generation reliably despite unstable service conditions.

Tasks:

- submit only selected shots
- skip already completed outputs
- preserve append-only logs
- detect repeated failure conditions
- enforce backoff and stop policies
- expose a clear run report to the user

Definition of done:

- long video-generation runs can be resumed safely
- service instability does not corrupt pipeline state

## Phase 10 - Mixed Cut Assembly

Goal:
Render final video from the scene plan using videos when available and stills otherwise.

Tasks:

- select render source per shot from canonical data
- generate clip-level intermediates
- concatenate via manifest
- cut audio to project or partial-cut boundary
- support partial and full deliveries

Definition of done:

- final render matches the canonical scene order and timing
- no manual asset picking is required

## Phase 10.5 - Publishing Asset Generation

Goal:
Generate the final publication package around the rendered video.

Tasks:

- create candidate video titles
- create candidate descriptions
- create thumbnail prompts from the approved narrative angle
- generate thumbnail images through FastGen
- store all candidates and final approved selections

Recommended timing:

- title and description drafts can be produced after the rewritten script and refined after the scene plan
- thumbnail generation should usually happen after the scene plan and near-final narrative positioning are clear
- final approval should happen before upload

Definition of done:

- each project has approved title, description, and thumbnail outputs ready for publishing

## Phase 11 - Automated Quality Control

Goal:
Add a hard validation layer before final delivery.

Tasks:

- verify every scene has a render source
- verify file existence and basic integrity
- verify total timings against transcript/audio
- detect overlong still holds
- detect manifest mismatches
- emit `qc_report.json`

Definition of done:

- pipeline can fail early before a broken final render is delivered
- user can inspect one concise QC result

## Phase 12 - Unified Runner

Goal:
Control the whole workflow from one command.

Tasks:

- build `scripts/run_pipeline.py`
- support stage-by-stage execution
- support resume from any completed stage
- support dry-run and validation-only modes
- produce a final summary report

Suggested stage sequence:

1. rewrite
2. transcribe
3. build_scene_plan
4. build_prompts
5. generate_images
6. normalize_images
7. select_animation_targets
8. generate_videos
9. build_mixed_cut
10. generate_publishing_drafts
11. generate_thumbnails
12. qc
13. final_render

Definition of done:

- one command can run the project end-to-end
- interrupted runs can continue without manual reconstruction

## Phase 13 - VPS and Background Execution

Goal:
Move the stable pipeline to unattended infrastructure after local reliability is proven.

Tasks:

- decide what should stay local and what should move remote
- set up environment variable management
- set up persistent logs
- set up job resume and monitoring
- separate compute-bound ffmpeg tasks from service-bound API waits

Definition of done:

- the pipeline can run unattended
- machine restarts or disconnects do not destroy progress

## Immediate Next Actions

These are the recommended next concrete steps from today.

1. Draft the canonical `project.json` structure.
2. Draft the canonical `scene_plan.json` structure.
3. Decide the project folder layout for future runs.
4. Identify which existing scripts can be reused unchanged.
5. Identify which existing scripts need wrappers versus refactors.
6. Build the first orchestration skeleton without yet changing every stage.

## Progress Checklist

Use this section as a lightweight status board.

- [x] Workflow memory captured in JSON
- [x] Operating rules documented
- [x] Main pipeline stages identified
- [x] Canonical `project.json` schema defined
- [x] Canonical `scene_plan.json` schema defined
- [ ] Per-project folder structure defined
- [ ] Rewrite-stage spec defined
- [ ] Publishing-stage spec defined
- [ ] QC spec defined
- [ ] Animation policy formalized
- [ ] Unified runner scaffold created
- [ ] Full end-to-end dry run completed
- [ ] VPS migration plan finalized

## How We Will Use This File

Whenever work resumes on this project, use this file to answer:

- what stage are we implementing now
- what dependencies must already exist
- what deliverable proves the stage is complete
- what still remains before end-to-end automation is real

If a new discovery changes the process, update this file so the roadmap stays honest.
