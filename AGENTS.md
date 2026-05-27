# AI Video Production Agents

This repository runs an SRT-first visual production pipeline for long-form YouTube videos with existing voice-over audio.

Canonical chain:

```text
audio + source transcript
→ Whisper SRT
→ cleaned.srt
→ scene_plan.json
→ prompt_package.json
→ llm_prompt_drafts.json
→ final_scene_plan.json
→ fastgen_prompts.md
→ image generation
→ timeline
→ final video
```

## Global Source Of Truth

Timing truth:

1. `cleaned.srt`
2. `scene_plan.json`

After `scene_plan.json` passes Scene QA, agents must not mutate:

- `scene_id`
- `start`
- `end`
- `duration`
- scene order

Creative work happens inside existing scenes.

## Core Rule

Prompts must come from real SRT timing, not abstract paragraphs.

Prompts must not:

- include spoken dialogue;
- ask characters to say the narration;
- include subtitles inside images;
- create lip-sync scenes;
- invent a new timing structure.

Visuals must support narration, not duplicate it mechanically.

## Required Project Files

Minimum input:

```text
/input/audio.mp3
/input/source_transcript.txt
/transcript/raw_whisper.srt
/transcript/cleaned.srt
```

Canonical planning outputs:

```text
/planning/scene_plan.json
/planning/prompt_package.json
/prompts/llm_prompt_drafts.json
/prompts/final_scene_plan.json
/exports/fastgen_prompts.md
```

## Required Scripts

Expected flow:

```text
cleanup_transcript_from_source.py
build_project_scene_plan.py
run_scene_qa.py
build_project_narrative_map.py
build_project_style_bible.py
build_project_visual_direction.py
build_project_continuity_bible.py
build_project_prompt_package.py
apply_llm_prompt_drafts.py
build_project_motion_plan.py
export_project_fastgen_prompts.py
run_final_review.py
run_project_fastgen_generation.py
normalize_project_images.py
build_project_slideshow_timeline.py
render_project_slideshow_video.ps1
```

## Non-Negotiable Rules

1. Timing comes from SRT.
2. `scene_plan.json` is canonical.
3. Visual Director does not create new timing.
4. Prompt Engineer writes for existing `scene_id` records.
5. Long scenes may contain internal beats, but parent `scene_id` stays stable.
6. Every `final_prompt` must match voice text, duration, narrative meaning, style, and continuity.
7. Prompts are silent visuals only.
8. No generic stock-photo look.
9. No random text, fake UI, malformed hands, or plastic faces.
10. Every prompt needs a visual reason to exist.

## Agent Files

Use role instructions from:

```text
agents/pipeline_architect.md
agents/transcript_timing_engineer.md
agents/scene_planner.md
agents/narrative_editor.md
agents/visual_director.md
agents/art_director_style_bible_keeper.md
agents/character_continuity_keeper.md
agents/prompt_engineer.md
agents/motion_director.md
agents/research_fact_check_agent.md
agents/brand_realism_supervisor.md
agents/scene_qa_agent.md
agents/prompt_qa_agent.md
agents/export_automation_engineer.md
agents/final_review_director.md
workflow/srt_first_video_workflow.md
prompts/system_master_prompt_for_codex.md
```
