# LLM Prompt Authoring Design

## Purpose

This document defines the prompt-authoring logic for the project:

- `Python` keeps orchestration, timing, manifests, validation, and export
- `LLM` owns project-level visual direction and final visual prompts

The goal is to keep Python as the production backbone while moving scene meaning, visual logic, and prompt writing into dedicated LLM stages.

## Core Principle

Production formula:

- `Whisper` = timing
- `source script` = meaning
- `scene_plan` = structured shot timing
- `Python` = structure, files, validation, export
- `LLM pass 1` = `visual_bible.json`
- `LLM pass 2` = `llm_prompt_drafts.json`

## Responsibility Split

### Python owns

- project creation
- transcription
- transcript cleanup/alignment
- scene splitting
- scene ids and timing
- neutral context packing for prompt writing
- writing and reading json files
- validation
- FastGen export
- image generation orchestration
- normalization and render

### LLM owns

- story interpretation
- main subject understanding
- project-level visual world
- recurring motifs
- continuity rules
- scene-role logic
- what should be in frame
- camera/composition choice
- lighting and mood
- final image prompt text

## New Prompt Authoring Model

The old rule-based model was:

- detect topic-specific keywords in Python
- assemble prompt fragments in Python

The new model is:

1. Python prepares a neutral `scene_context_pack.json`
2. LLM reads the full project and writes `visual_bible.json`
3. optional LLM shot-planning pass writes `visual_shot_plan.json`
4. optional LLM shot-level prompt pass writes `shot_prompt_package.json`
5. Python expands shot-level prompts back into `llm_prompt_drafts.json`
6. or the LLM writes `llm_prompt_drafts.json` directly in scene-level mode
7. Python validates and saves them
8. Python exports them to FastGen-ready format

For autonomous full-project rewriting, use:

- [codex_full_rewrite_operator_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/codex_full_rewrite_operator_prompt.md)
- [visual_shot_plan_operator_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/visual_shot_plan_operator_prompt.md)
- [shot_prompt_package_operator_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/shot_prompt_package_operator_prompt.md)

## Neutral Scene Context Pack

The context pack should stay neutral and production-focused.

Suggested scene fields:

```json
{
  "project_id": "priroda_full_001",
  "scene_id": "scene_0042",
  "shot_index": 42,
  "start": 125.4,
  "end": 129.8,
  "duration": 4.4,
  "voice_text": "Die Weibchen sitzen oft auf Bäumen und fressen Blätter.",
  "context_before": "Für uns wirkt die Nachtluft leer. Für ihn ist sie voller Spuren.",
  "context_after": "Die Männchen dagegen beginnen in der Dämmerung um die Baumkronen zu fliegen.",
  "source_language": "de",
  "prompt_language": "English",
  "scene_archetype_hint": null,
  "project_theme": null,
  "style_summary": "Ultra-realistic cinematic documentary still, natural light, rich organic textures, realistic anatomy when relevant, shallow depth of field when useful, 16:9 composition, no text.",
  "master_subject": "European cockchafer beetle",
  "story_arc_summary": "A documentary about the cockchafer life cycle: emergence, flight, mating, predators, underground larva, metamorphosis, anatomy, history, nostalgia.",
  "previous_role_hint": "mating_search",
  "next_role_hint": "predator_threat"
}
```

The context pack should be built by Python, not by hand.

It should not contain brittle, topic-specific hardcoded rails such as insect-only life-stage logic.

## Visual Bible Stage

Before prompt drafting, the LLM should write:

- `prompts/visual_bible.json`

The visual bible should define:

- main subject
- subject type
- visual world
- recurring motifs
- continuity rules
- project-level forbidden mistakes
- scene-role taxonomy
- high-level visual blocks

This allows the second LLM pass to stay consistent without relying on Python keyword rules.

Suggested visual-bible files:

- `prompts/visual_bible.json`
- `prompts/visual_bible_review.md`
- [visual_bible_master_prompt.md](C:/Users/MIKE/Documents/Codex/YT/deliverables/visual_bible_master_prompt.md)

## LLM Prompt Draft Output Contract

The prompt-authoring pass should return structured JSON, not prose.

Exact per-scene output:

```json
{
  "scene_id": "scene_0042",
  "visual_goal": "Show the female cockchafer as part of a feeding and mating-context scene in the tree canopy.",
  "shot_role": "mating_search",
  "primary_subject": "female cockchafer on fresh leaves",
  "secondary_subjects": [
    "spring leaves",
    "tree branch"
  ],
  "what_is_in_frame": "A female cockchafer sits on soft green leaves in the evening canopy, feeding while the surrounding branches hint at the dusk mating environment.",
  "camera": "close documentary nature shot",
  "composition": "the beetle is clear but not oversized, leaves frame the subject naturally",
  "lighting": "soft evening light with natural warm highlights",
  "mood": "quiet, watchful, seasonal",
  "continuity_notes": "Keep the same documentary world as neighboring scenes, but do not repeat the exact same beetle-on-branch composition.",
  "negative_prompt": "text, watermark, unrelated animals, generic fantasy insect",
  "final_prompt": "Close documentary nature still of a female cockchafer feeding on fresh spring leaves in a European tree canopy at dusk..."
}
```

This output contract should be treated as exact, not approximate.
If a field is unknown, return an empty string or empty list instead of omitting the field.

## Batch Strategy

The LLM should not write prompts one scene at a time without context.

Preferred batching:

- 8 to 20 scenes per batch
- each batch should include:
  - scene records from `scene_context_pack.json`
  - the current `visual_bible.json`
  - neighboring context
  - style summary

This lets the LLM preserve continuity while avoiding repetition.

Additional full-pass rules:

- Do not reuse a successful batch prompt template mechanically. Use `visual_bible` roles and `visual_blocks` to vary subject, action, composition, camera distance, and emotional function across neighboring scenes.
- When scenes are short, do not force a completely new visual concept for every tiny phrase. Preserve continuity across adjacent micro-scenes, but vary framing or function when the narration changes action, life stage, threat, or emotional mode.

## New Pipeline Placement

The intended pipeline becomes:

```text
audio
-> whisper
-> cleanup_transcript_from_source
-> scene_plan
-> build_prompt_package
-> build_scene_context_pack
-> llm_visual_bible
-> optional llm_visual_shot_plan
-> optional llm_shot_prompt_package
-> optional expand_shot_prompts_to_scene_drafts
-> llm_prompt_authoring
-> apply_llm_prompt_drafts
-> validate_prompts
-> export_fastgen_prompts
-> generate_images
-> normalize_images
-> build_timeline
-> render_video
```

## New Artifacts

Suggested prompt-stage files:

- `prompts/scene_context_pack.json`
- `prompts/visual_bible.json`
- `prompts/visual_bible_review.md`
- `prompts/visual_shot_plan.json`
- `prompts/shot_prompt_package.json`
- `prompts/shot_prompt_review.md`
- `prompts/llm_prompt_drafts.json`
- `prompts/llm_prompt_drafts_v2_in_progress.json`
- `prompts/llm_prompt_rewrite_status.json`
- `prompts/full_rewrite_batch_plan.json`
- `prompts/prompt_package.json`
- `prompts/prompt_review.md`
- `prompts/fastgen_prompts_generator_ready.md`

## Python Bridge

Python should not write the final creative prompts.

Python should:

1. read `scene_context_pack.json`
2. save `visual_bible.json`
3. accept `llm_prompt_drafts.json`
4. merge the LLM-authored prompt fields into `prompt_package.json`
5. validate required fields
6. export FastGen-ready prompt blocks

This means the real transport chain is:

`scene_context_pack.json -> visual_bible.json -> llm_prompt_drafts.json -> Python ingestion -> FastGen`

Optional phase-2 transport chain:

`scene_context_pack.json -> visual_bible.json -> visual_shot_plan.json -> shot_prompt_package.json -> expand_shot_prompts_to_scene_drafts.py -> llm_prompt_drafts.json -> Python ingestion -> FastGen`

## Validation Requirements

Python validation should check:

- every scene has one prompt record
- every prompt record has `scene_id`
- `final_prompt` is not empty
- `visual_goal` is not empty
- `primary_subject` is not empty
- prompt language matches the configured language
- prompt package count matches scene count

Validation should not try to judge creativity in P0.

For autonomous full rewrite, add a batch-level self-QC loop:

- draft batch prompts
- write batch review markdown
- write batch review json
- only merge passing batches into the in-progress rewrite file

## Immediate Implementation Direction

The next scalable step is not a Python `subject_profile.json`.

The better step is:

1. keep Python neutral
2. add a project-level LLM `visual_bible.json`
3. use the visual bible to guide batch prompt authoring

This keeps the system clean:

- Python remains the backbone
- the LLM becomes the visual director
