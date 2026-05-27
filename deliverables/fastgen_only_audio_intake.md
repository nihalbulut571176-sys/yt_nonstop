# FastGen-Only Audio Intake

## Purpose

This flow prepares a new `fastgen_only` project from an audio source and gets it ready for the next production stages.

It is intended for the mode:

- audio provided
- no VNonStop animation
- still-image generation through FastGen
- direct slideshow montage after images are ready

## What The Bootstrap Script Does

Script:

- `scripts/bootstrap_fastgen_only_project.py`

It:

1. creates a new project folder under `projects/<project_id>/`
2. accepts an audio source as a local path or `http(s)` URL
3. stores the audio inside the project
4. creates `project.json`
5. creates publishing scaffolds for:
   - title drafts
   - description drafts
   - thumbnail brief
   - thumbnail prompt candidates
6. runs Whisper transcription unless `--skip-transcribe` is used

## Command Example

```powershell
python scripts/bootstrap_fastgen_only_project.py `
  --project-id telegram_fastgen_001 `
  --audio-source "C:\path\to\voiceover.mp3"
```

Example with URL:

```powershell
python scripts/bootstrap_fastgen_only_project.py `
  --project-id telegram_fastgen_001 `
  --audio-source "https://example.com/audio.mp3"
```

Optional raw text:

```powershell
python scripts/bootstrap_fastgen_only_project.py `
  --project-id telegram_fastgen_001 `
  --audio-source "C:\path\to\voiceover.mp3" `
  --raw-text-path "C:\path\to\raw_text.md"
```

## Resulting Structure

The script creates:

- `projects/<id>/project.json`
- `projects/<id>/audio/`
- `projects/<id>/transcript/`
- `projects/<id>/scene_plan/`
- `projects/<id>/prompts/`
- `projects/<id>/images/`
- `projects/<id>/renders/`
- `projects/<id>/publishing/`
- `projects/<id>/logs/`

Publishing files created automatically:

- `publishing/title_drafts.json`
- `publishing/title_approved.txt`
- `publishing/description_drafts.json`
- `publishing/description_approved.md`
- `publishing/thumbnail_brief.md`
- `publishing/thumbnail_prompt_candidates.json`
- `publishing/thumbnail_prompt_approved.txt`
- `publishing/thumbnails/run_manifest.json`

## Next Production Steps After Intake

Once audio intake and transcription are complete:

1. clean the transcript against source text when source text exists
2. build the scene plan from the cleaned timed transcript
3. build the prompt package for all scenes
4. auto-draft prompts in one global visual style
5. prepare the publishing package for title, description, and thumbnail generation
6. export the prompt package into generator-ready FastGen blocks
7. run project-aware FastGen still-image generation
8. normalize images
9. build slideshow timeline
10. render final slideshow video
11. finalize title, description, and thumbnail

## One-Command Backbone

The project now has a unified runner:

- `scripts/run_fastgen_only_project.py`

And a minimal validator:

- `scripts/validate_project.py`

Example:

```powershell
python scripts/run_fastgen_only_project.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json" `
  --from cleanup_transcript_from_source `
  --to render
```

Resume example:

```powershell
python scripts/run_fastgen_only_project.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json" `
  --resume
```

Validation example:

```powershell
python scripts/validate_project.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json" `
  --stage all
```

Transcript quality gate:

```powershell
python scripts/validate_project.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json" `
  --stage transcript_quality
```

## Post-Transcription Commands

Run transcript cleanup/alignment:

```powershell
python scripts/cleanup_transcript_from_source.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

Build the project scene plan:

```powershell
python scripts/build_project_scene_plan.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

Prepare title/description/thumbnail package:

```powershell
python scripts/prepare_project_publishing_package.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

Build the prompt package:

```powershell
python scripts/build_project_prompt_package.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

Draft global-style visual prompts:

```powershell
python scripts/draft_project_visual_prompts.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

Export the prompt package into FastGen-ready blocks:

```powershell
python scripts/export_project_fastgen_prompts.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

## Slideshow Montage Commands

Build timeline from `scene_plan.json`:

```powershell
python scripts/build_project_slideshow_timeline.py `
  --project-json "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

Render the final slideshow:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/render_project_slideshow_video.ps1 `
  -ProjectJson "C:\Users\MIKE\Documents\Codex\YT\projects\telegram_fastgen_001\project.json"
```

## Current Scope

This flow now covers:

- project bootstrap from audio
- optional raw-text intake
- Whisper transcription
- transcript cleanup/alignment quality gate
- project-aware scene-plan generation
- project-aware prompt-package generation
- project-aware prompt drafting in a unified style
- project-aware publishing package preparation
- unified stage runner
- stage validation
- project-aware still-image generation adapter
- project-aware image normalization
- slideshow timeline build
- final slideshow render

The remaining big quality layer is not technical backbone anymore, but creative refinement:

- better prompt filling
- richer thumbnail/title/description generation
- selective scene regeneration
- stronger QC heuristics
