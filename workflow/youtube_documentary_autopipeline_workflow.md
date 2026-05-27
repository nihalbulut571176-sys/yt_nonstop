# YouTube Documentary Autopipeline Workflow

## Goal

This workflow is the top-level entrypoint for the production path:

```text
audio + transcript
-> timing-aware scene plan
-> narrative and visual planning
-> LLM-authored prompt drafts
-> FastGen still generation
-> motion plan
-> slideshow timeline
-> final rendered YouTube video
```

It is designed for long-form documentary-style YouTube videos where the images must feel directed, varied, and tightly aligned to the voice-over rather than literal stock-photo illustration.

## Entry Script

Use:

```powershell
python scripts/run_youtube_documentary_workflow.py `
  --project-id pink_panthers_ep01 `
  --audio-source C:\path\to\voiceover.mp3 `
  --raw-text-path C:\path\to\transcript.txt `
  --auto-author-llm `
  --soften-policy-prompts
```

The script performs:

1. workspace preflight
2. `.env` loading without exposing secrets
3. `ffmpeg` and `ffprobe` checks
4. missing-input reporting
5. project bootstrap
6. staged pipeline execution through `scripts/run_fastgen_only_project.py`

## Required Inputs

Minimum expected inputs:

```text
.env
audio file
raw transcript text
ffmpeg on PATH
ffprobe on PATH
```

If transcript text is missing, the workflow can still proceed from audio timing, but prompt quality and semantic alignment may be weaker.

## Reports

The workflow writes:

- `logs/input_check_report.md`
- `logs/missing_inputs_report.md` when startup is blocked
- downstream stage reports already produced by the existing pipeline

## Recommended Run Modes

Full run:

```powershell
python scripts/run_youtube_documentary_workflow.py `
  --project-id demo_project `
  --audio-source C:\path\voice.mp3 `
  --raw-text-path C:\path\transcript.txt `
  --auto-author-llm `
  --to render
```

Preflight only:

```powershell
python scripts/run_youtube_documentary_workflow.py `
  --project-id demo_project `
  --audio-source C:\path\voice.mp3 `
  --raw-text-path C:\path\transcript.txt `
  --preflight-only
```

Resume an interrupted project:

```powershell
python scripts/run_youtube_documentary_workflow.py `
  --project-id demo_project `
  --resume `
  --auto-author-llm
```

## Intended Production Behavior

- Build from timing first, not from untimed prose.
- Treat each beat as a visual function, not a literal noun extraction.
- Prefer cinematic documentary realism over generic illustration.
- Use prompt variation and QC to avoid slideshow repetition.
- Keep the final output renderable from a single project manifest.
