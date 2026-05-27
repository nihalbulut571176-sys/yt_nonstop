# Visual Bible Master Prompt

Use this prompt when the pipeline has already created:

- `scene_plan.json`
- `prompt_package.json`
- `scene_context_pack.json`

and the next LLM step must author:

- `prompts/visual_bible.json`

## Purpose

This stage exists to keep `Python` neutral.

- `Python` should not decide what the documentary is visually about
- `Python` should not hardcode insect, mammal, ocean, or history-specific rails
- `LLM` should read the full project context and define the visual world

The visual bible becomes the project-wide source of truth for:

- subject understanding
- visual world
- recurring motifs
- continuity rules
- project-level mistakes to avoid
- high-level scene-role taxonomy
- major visual blocks across the story

## Input Contract

You will receive:

- the full narration or approved script when available
- `scene_context_pack.json`
- optional `style_guide.json`
- optional notes about generator constraints

Treat `scene_context_pack.json` as the source of truth for:

- `scene_id`
- timing windows
- local narration text
- source language
- prompt language
- project-level style summary

Do not invent or change `scene_id`, timing, or project metadata.

## Task

Read the whole project as a documentary story.

Before writing per-scene prompts, define the visual logic of the entire film:

1. What is the real main subject?
2. What kind of visual world should the audience feel?
3. What recurring motifs help unify the film?
4. What mistakes would break the documentary?
5. What broad visual blocks does the story move through?
6. What scene-role vocabulary will help the later prompt-authoring pass stay consistent without becoming repetitive?

## Output Rules

Return valid machine-readable JSON only.

Use this exact structure:

```json
{
  "project_id": "string",
  "main_subject": "string",
  "subject_type": "string",
  "visual_world": "string",
  "style_summary": "string",
  "prompt_language": "English",
  "recurring_motifs": [],
  "continuity_rules": [],
  "forbidden_mistakes": [],
  "scene_role_taxonomy": [],
  "visual_blocks": [
    {
      "block_id": "block_01",
      "label": "string",
      "purpose": "string",
      "scene_id_range": ["scene_0001", "scene_0018"],
      "notes": "string"
    }
  ],
  "global_negative_prompt": []
}
```

## Field Guidance

### `main_subject`

Concrete subject, not just a poetic title.

Good:

- `European cockchafer beetle`
- `gray wolf`
- `giant Pacific octopus`
- `Pompeii and the eruption of Vesuvius`

Bad:

- `A life lived twice`
- `Nature is mysterious`

### `subject_type`

Short universal category.

Examples:

- `insect`
- `mammal`
- `bird`
- `marine_animal`
- `plant`
- `fungus`
- `place`
- `historical_topic`
- `scientific_process`

### `visual_world`

Describe the cinematic world of the project in one compact paragraph.

This should define:

- environment feeling
- documentary tone
- realism level
- lighting tendencies
- visual atmosphere

### `recurring_motifs`

List 4 to 10 motifs that can recur naturally across the film.

Examples:

- `tracks in snow`
- `wet roots in dark soil`
- `dusk canopy movement`
- `old engraved paper textures`

### `continuity_rules`

Rules that keep the project coherent while avoiding repetitive framing.

Examples:

- `Keep the same documentary world across scenes, but vary shot scale and subject distance.`
- `Do not let every scene become a centered hero portrait.`
- `When the narration changes life stage or story phase, the image must also change.`

### `forbidden_mistakes`

Project-level things that would break trust.

Examples:

- `Do not confuse larva scenes with fully developed adult beetles.`
- `Do not turn documentary wildlife into fantasy creature imagery.`
- `Do not show a domestic dog when the topic is a wild wolf unless the narration explicitly mentions human proximity.`

### `scene_role_taxonomy`

Short reusable scene roles for later prompt writing.

Examples:

- `atmospheric_intro`
- `habitat_establish`
- `feeding_behavior`
- `anatomy_macro`
- `threat_presence`
- `historical_context`
- `nostalgic_closing`

### `visual_blocks`

Split the story into high-level blocks, not per-scene prompts.

Each block should explain:

- where the film is in its arc
- what the viewer should feel
- what type of imagery dominates that section

### `global_negative_prompt`

Short project-wide negatives only.

Examples:

- `text`
- `watermark`
- `logo`
- `cartoon`
- `fantasy creature`

## Quality Rules

- Keep the bible universal enough that it can guide many scenes.
- The visual bible must be specific enough to prevent generic prompts, but broad enough to work across all scenes.
- Do not write per-scene prompts here.
- Do not repeat the same phrase in every field.
- Use the existing `style_summary` if provided.
- If the script suggests a different environment than a default documentary look, follow the script.
- Write all free-text fields in `prompt_language`, unless a field is clearly metadata.
- Do not use an existing legacy `llm_prompt_drafts.json` as a creative source if it exists; base the bible on the narration, `scene_context_pack.json`, and style requirements.

## Final Instruction

Act as a documentary visual director, not a prompt spammer.

First understand the entire story world.
Then output a compact, production-usable `visual_bible.json` that a later per-scene prompt pass can follow.
