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
2. generate visual prompts for all shots
3. run FastGen for still images
4. normalize images
5. build slideshow timeline
6. render final slideshow video
7. finalize title, description, and thumbnail

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

This intake flow prepares the project and launches transcription.

Prompt generation, scene-plan generation, FastGen image generation, and publishing-text drafting are still subsequent stages, but they now have a clean per-project home and a stable manifest to build on.
