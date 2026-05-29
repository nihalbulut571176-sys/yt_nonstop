# golden_60s

Deterministic no-API sample project for the `yt_nonstop` production workflow.

Purpose:
- exercise the visual video pipeline end to end without external API calls;
- provide a stable 60–90 second regression fixture;
- keep all timing grounded in SRT while using heuristic/file/fake providers only.

Primary source:
- [project.json](./project.json)
- [input/source.srt](./input/source.srt)

The golden test hydrates the rest of the project in a temp workspace and runs:
- narration beats
- authored narration beats
- visual allocation
- generation estimate
- visual shot plan
- frame briefs
- prompt drafts
- generation lock
- fake generation
- image QC
- regeneration plan
- fake regeneration execution
- continuity QC
- review package
- review decisions
- timeline
- render dry-run
- production report
- dashboard

The sample is intentionally API-free:
- no real LLM
- no real VLM
- no real image generation
- no real render invocation beyond dry-run validation
