# Production Workflow

This is the practical end-to-end workflow we converged on for narrated investigative videos.

## Core Flow

1. Prepare a per-project folder with `input/work/images/output`
2. Load or create source text and audio
3. Transcribe / normalize text inputs as needed
4. Build the scene plan
5. Build frame briefs and prompt artifacts
6. Export generation batches
7. Generate images with FastGen
8. Run QC and review
9. Build timeline and render
10. Optionally replace part of the head with pre-rendered motion clips and stitch the tail back on

## Stage Notes

### Transcribe

Use the real audio as the timing source when timing accuracy matters.

### Beats / Scene Plan

The planning layer should define semantic beats clearly enough that image prompts and downstream render logic stay aligned with the spoken narration.

### Align / Timeline

The timeline must remain monotonic and dense enough that rendering does not create artificial long holds.

### Prompts

Prompts should be generated from the clean semantic source, not from low-quality subtitle drift.

### Generate Images

FastGen runs are operator-controlled and resumable.

The real run model now includes:
- route-aware generation support
- resumable manifests and state
- deterministic prompt repair / auditing helpers
- optional reference routing for human-centric shots

### Render

The standard render path is still-image driven.

An optional hybrid path is also supported operationally:
- replace the first N shots with pre-rendered video clips
- cut the original full render at the matching shot boundary
- stitch the rebuilt head and preserved tail back together

## Final Image Hygiene

During iteration, `images/` may contain:
- current images
- stale images from older shot IDs
- test outputs

For any final delivery, export a clean `final_images/` set derived from the current `shot_timeline`.

## Operator Defaults

- keep heavy outputs in local workspace folders
- commit code/docs/specs, not bulky media
- validate timing before expensive full-length image generation
- use lightweight samples in repo for reproducibility
