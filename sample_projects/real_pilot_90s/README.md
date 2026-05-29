# real_pilot_90s

Bootstrap profile for a real 60-90 second narrated pilot project that starts from an existing SRT and optional audio file.

Purpose:
- create a repeatable SRT-first pilot workspace for real footage timing;
- keep external LLM, VLM, and image-generation providers disabled by default;
- leave the project ready to enable providers later without changing the project shape.

Bootstrap command:

```powershell
python scripts/bootstrap_real_pilot_project.py `
  --project-root C:\path\to\pilot_project `
  --source-srt C:\path\to\source.srt `
  --source-audio C:\path\to\source_audio.mp3 `
  --profile no_vlm_production
```

What it creates:
- `input/source.srt`
- `input/source_audio.*` when audio is provided
- `transcript/raw_whisper.srt`
- `transcript/cleaned.srt`
- `project.json`
- the standard artifact folders used by `yt-nonstop status` and later production stages

Default behavior:
- no real LLM provider
- no real VLM provider
- no real image generation provider
- render dry-run enabled
- manual review allowed without VLM

Next commands after bootstrap:

```powershell
yt-nonstop run --project-json C:\path\to\pilot_project\project.json --to production_report
yt-nonstop status --project-json C:\path\to\pilot_project\project.json
```

Checklist for enabling real providers later:
1. Set `project.providers.llm_provider.mode` to `file`, `command`, `http`, or `openai_compatible`.
2. Update `planning.narration_beats_llm`, `planning.visual_allocation_llm`, or `prompts.prompt_authoring_llm` if a stage needs its own provider config.
3. Switch `planning.visual_allocation_provider` away from `disabled` when you want provider-authored allocation.
4. Change `qc.image_semantic_qc_mode` from `disabled` to `heuristic` or `external`.
5. Replace `images.provider` and `generation.image_generation_mode` with a real image backend before generation.
6. Set `workflow.render_dry_run` to `false` only when render inputs and external outputs are ready.
