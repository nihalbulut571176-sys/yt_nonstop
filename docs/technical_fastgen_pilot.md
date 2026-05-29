# Technical FastGen Pilot

This document covers the first real-image pilot modes for `yt_nonstop`.

Pilot modes:
- `technical_fastgen_pilot`: LLM off, VLM off by default, real FastGen allowed only with `--real-generation`.
- `full_creative_pilot`: LLM on through the unified provider, VLM off by default, real FastGen still requires `--real-generation`.

Both modes are operator-only manual runs. Pytest must continue using fake providers only.

## Purpose

Use these pilots to validate a real capped FastGen batch end to end:
- real image generation
- resumable state and run manifests
- image QC
- regeneration plan
- review package
- timeline build
- motion render dry-run
- production report

The first pilot should stay small: 10 to 15 generative frames.

## Required environment

FastGen:
- `FAST_GEN_API_KEY`

Optional LLM for `full_creative_pilot`:
- `YT_NONSTOP_LLM_PROVIDER_MODE`
- `YT_NONSTOP_LLM_PROVIDER_API_KEY`
- `YT_NONSTOP_LLM_PROVIDER_BASE_URL`
- `YT_NONSTOP_LLM_PROVIDER_MODEL`

Optional external VLM later:
- keep `qc.image_semantic_qc_mode=disabled` for the first pilot
- enable external VLM only after the image-only pilot is stable

## Bootstrap a real pilot project

```powershell
python scripts/bootstrap_real_pilot_project.py `
  --project-root C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001 `
  --source-srt C:\path\to\source.srt `
  --source-audio C:\path\to\source_audio.mp3 `
  --profile no_vlm_production
```

Then build the planning/calibration artifacts needed before real generation.

## Preflight

Run preflight before any real FastGen call:

```powershell
python scripts/preflight_real_generation.py `
  --project-json C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001\project.json `
  --profile technical_fastgen_pilot `
  --limit-frames 15 `
  --real-generation
```

Preflight checks:
- project loads
- visual allocation exists
- visual calibration report exists
- prompt export and batches exist
- safe frame cap exists
- FastGen credentials exist
- output dirs exist
- `--real-generation` is present

## Technical FastGen Pilot

Generate the first 10 to 15 real frames with LLM and VLM still off:

```powershell
yt-nonstop run `
  --project-json C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001\project.json `
  --from export_generation_batches `
  --to generate_images `
  --profile technical_fastgen_pilot `
  --resume `
  --limit-frames 15 `
  --real-generation
```

Equivalent legacy wrapper:

```powershell
python scripts/run_fastgen_only_project.py `
  --project-json C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001\project.json `
  --from export_generation_batches `
  --to generate_images `
  --profile technical_fastgen_pilot `
  --resume `
  --limit-frames 15 `
  --real-generation
```

## Full Creative Pilot

Use this only when the project already has valid LLM provider config:

```powershell
yt-nonstop run `
  --project-json C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001\project.json `
  --from generate_fastgen_prompt_drafts `
  --to generate_images `
  --profile full_creative_pilot `
  --resume `
  --limit-frames 15 `
  --real-generation
```

Notes:
- LLM authoring is on by default in `full_creative_pilot`.
- VLM stays off by default for the first creative pilot.
- Real FastGen still requires `--real-generation`.

## QC, review, and render dry-run

After a limited generation batch:

```powershell
yt-nonstop run `
  --project-json C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001\project.json `
  --from image_qc `
  --to production_report `
  --profile technical_fastgen_pilot `
  --resume `
  --render-dry-run
```

This run should:
- run image QC
- build the regeneration plan
- build the review package
- build a timeline from available selected images
- write a render dry-run report
- write a production report

If only a capped subset was generated, the reports should show that this is a partial pilot rather than a full production render.

## Artifacts to inspect

Review these files after the pilot:
- `images/run/run_manifest.json`
- `qc/image_qc_report.json`
- `qc/selected_images_manifest.json`
- `qc/review_package.html`
- `renders/edit_decision_list.json`
- `reports/production_report.md`

Helpful status command:

```powershell
yt-nonstop status --project-json C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001\project.json
```

## Retry failed frames

Retry only failed frames:

```powershell
yt-nonstop run `
  --project-json C:\Users\MIKE\Documents\Codex\YT\projects\real_pilot_001\project.json `
  --from generate_images `
  --to generate_images `
  --profile technical_fastgen_pilot `
  --resume `
  --retry-failed-only `
  --real-generation
```

## Safe resume

Resume skips already successful frames automatically:
- successful frames in pipeline state are not regenerated
- successful image files already on disk are not regenerated
- capped pilot runs can be resumed with the same or a smaller batch safely

## Avoid accidental API spend

Rules:
- always use `--real-generation` explicitly
- always keep `--limit-frames` between 10 and 15 for the first pilot
- do not start with `full_creative_pilot` until the technical pilot is stable
- keep `--render-dry-run` on until the subset looks correct
- inspect `run_manifest.json` after each run before widening the cap
