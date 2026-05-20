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

1. build the scene plan from the real transcript timing
2. prepare the publishing package for title, description, and thumbnail generation
3. generate visual prompts for all shots
4. run FastGen for still images
5. normalize images
6. build slideshow timeline
7. render final slideshow video
8. finalize title, description, and thumbnail

## Post-Transcription Commands

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
- project-aware scene-plan generation
- publishing package preparation

FastGen prompt generation, still-image generation, normalization, and final slideshow rendering remain the next execution stages, but they now have a clean per-project home and a stable manifest to build on.
