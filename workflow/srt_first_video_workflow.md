# SRT-First YouTube Visual Production Workflow

## Core Principle

The visual pipeline is built from real audio timing.

```text
audio + source transcript
→ raw_whisper.srt
→ cleaned.srt
→ scene_plan.json
→ Scene QA
→ narrative enrichment
→ style bible
→ visual direction
→ continuity
→ prompt_package.json
→ llm_prompt_drafts.json
→ Prompt QA
→ final_scene_plan.json
→ motion_plan.json
→ fastgen_prompts.md
→ Final Review
→ image generation
→ normalized stills
→ timeline
→ final video
```

## Canonical Rule

After Scene QA approval, `scene_id`, `start`, `end`, `duration`, and scene order are immutable.

## Responsible Stages

1. `Pipeline Architect`: validate workspace and canonical paths.
2. `Transcript & Timing Engineer`: produce `cleaned.srt`.
3. `Scene Planner`: build `scene_plan.json`.
4. `Scene QA Agent`: approve or reject scene structure.
5. `Narrative Editor`: add meaning, emotion, and retention logic.
6. `Art Director`: create `style_bible.md` and style guide JSON.
7. `Visual Director`: define visual strategy and shot logic.
8. `Character & Continuity Keeper`: keep recurring motifs coherent.
9. `Prompt Engineer`: write timed prompts through `llm_prompt_drafts.json`.
10. `Prompt QA Agent`: reject weak, literal, unsafe, or silent-breaking prompts.
11. `Motion Director`: create motion plan per scene.
12. `Export & Automation Engineer`: export `fastgen_prompts.md`.
13. `Final Review Director`: approve package for generation.
14. Downstream runtime: generate images, normalize, build timeline, render MP4.

## Definition Of Done

The pipeline is done when these artifacts exist:

```text
transcript/cleaned.srt
planning/scene_plan.json
planning/prompt_package.json
prompts/llm_prompt_drafts.json
prompts/final_scene_plan.json
motion/motion_plan.json
exports/fastgen_prompts.md
renders/<project>.mp4
logs/final_review_report.md
```
