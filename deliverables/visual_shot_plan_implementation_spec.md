# Visual Shot Plan Implementation Spec

## Purpose

This document defines the phase-1 architecture for adding shot-level visual planning on top of the existing scene-level FastGen pipeline.

The goal is to reduce unnecessary prompt uniqueness without breaking the current compatible path:

```text
scene_context_pack.json
-> visual_bible.json
-> visual_shot_plan.json
-> shot_prompt_package.json
-> expand_shot_prompts_to_scene_drafts.py
-> llm_prompt_drafts.json
-> apply_llm_prompt_drafts.py
-> export_project_fastgen_prompts.py
```

In phase 1, render and generation remain scene-compatible. The new shot layer is additive and reversible.

## Source-Of-Truth Hierarchy

```text
scene_plan.json
= timing truth

scene_context_pack.json
= scene context truth

visual_bible.json
= visual direction truth

visual_shot_plan.json
= montage-visual reuse truth

shot_prompt_package.json
= unique-shot prompt authoring contract

prompt_package.json
= backward-compatible scene contract
```

`visual_shot_plan.json` does not replace `visual_bible.json`.
It decides which visual shot serves which scenes.

## Quality Modes

Supported planning modes:

- `premium`
- `standard`
- `fast`

Behavior:

- `premium`: every scene is unique
- `standard`: hero unique, supporting mostly unique, continuity and bridge may reuse or derive
- `fast`: hero unique, supporting more often derived, continuity and bridge heavily reused

Target unique-shot ratios:

- `premium`: 100%
- `standard`: 45-65%
- `fast`: 25-40%

## Scene Importance

Allowed `scene_importance` values:

- `hero`
- `supporting`
- `continuity`
- `bridge`
- `reuse`

Guidance:

- `hero`: must stay unique
- `supporting`: usually unique in `standard`, may be derived in `fast`
- `continuity`: may reuse a shared motif
- `bridge`: may reuse a shared atmospheric motif
- `reuse`: intentionally inherits another shot

## Generation Modes

Allowed `generation_mode` values:

- `unique`
- `derived`
- `reused`

Meaning:

- `unique`: primary shot with its own full prompt
- `derived`: prompt can inherit a base shot plus a small variation note
- `reused`: no independent full prompt, only references another shot asset

## `visual_shot_plan.json`

Minimal schema:

```json
{
  "project_id": "example_project",
  "quality_mode": "standard",
  "total_scenes": 262,
  "target_unique_shots": 128,
  "actual_unique_shots": 0,
  "planning_source": "visual_bible.json",
  "scene_groups": [],
  "shots": [],
  "scene_to_shot": {}
}
```

### `scene_groups`

Grouping object:

```json
{
  "group_id": "group_012",
  "importance": "continuity",
  "visual_strategy": "one shared canopy-search motif with mild framing variation",
  "shot_id": "shot_023",
  "scenes": ["scene_0047", "scene_0048", "scene_0049"],
  "variation_notes": {
    "scene_0048": "slightly tighter crop",
    "scene_0049": "same branch motif, more open air"
  }
}
```

### `shots`

Shot object:

```json
{
  "shot_id": "shot_023",
  "importance": "continuity",
  "generation_mode": "unique",
  "primary_scene_id": "scene_0047",
  "scene_ids": ["scene_0047", "scene_0048", "scene_0049"],
  "visual_anchor": "male cockchafer quietly landing near female among leaves",
  "off_topic_risk": "low",
  "prompt_strategy": "one concrete documentary shot, no metaphor",
  "primary_subject": "male cockchafer near female in evening canopy"
}
```

### `scene_to_shot`

Fast lookup index:

```json
{
  "scene_0047": {
    "shot_id": "shot_023",
    "generation_mode": "unique",
    "source_shot_id": "shot_023",
    "variation_note": ""
  },
  "scene_0048": {
    "shot_id": "shot_023",
    "generation_mode": "derived",
    "source_shot_id": "shot_023",
    "variation_note": "slightly tighter crop"
  }
}
```

## `shot_prompt_package.json`

This file holds unique-shot prompt authoring inputs and outputs.

Minimal schema:

```json
{
  "project_id": "example_project",
  "quality_mode": "standard",
  "total_shots": 128,
  "shots": [
    {
      "shot_id": "shot_023",
      "primary_scene_id": "scene_0047",
      "scene_ids": ["scene_0047", "scene_0048", "scene_0049"],
      "importance": "continuity",
      "generation_mode": "unique",
      "visual_anchor": "male cockchafer quietly landing near female among leaves",
      "primary_subject": "male cockchafer near female in evening canopy",
      "what_is_in_frame": "male cockchafer landing near female among dusk leaves",
      "visual_goal": "show a quiet mating-nearby canopy beat",
      "base_prompt": "",
      "prompt_strategy": "one concrete documentary shot, no metaphor",
      "off_topic_risk": "low"
    }
  ]
}
```

In phase 1, `base_prompt` may be copied from the primary scene prompt for compatibility.

## Scene-Level Expansion Adapter

`expand_shot_prompts_to_scene_drafts.py` converts:

```text
visual_shot_plan.json + shot_prompt_package.json
```

into:

```text
llm_prompt_drafts.json
```

This keeps the existing `apply_llm_prompt_drafts.py` ingestion contract stable.

Adapter output record:

```json
{
  "scene_id": "scene_0048",
  "visual_goal": "show a quiet mating-nearby canopy beat",
  "final_prompt": "Ultra-realistic cinematic documentary still ... Same motif, slightly tighter crop.",
  "shot_id": "shot_023",
  "scene_importance": "continuity",
  "primary_subject": "male cockchafer near female in evening canopy",
  "what_is_in_frame": "male cockchafer landing near female among dusk leaves",
  "continuity_notes": "Derived from shot_023",
  "prompt_origin": "shot_prompt_package"
}
```

## Validation Rules

Required invariants:

1. Every `scene_id` from `scene_plan.json` must exist in `scene_to_shot`.
2. Every `scene_id` in `scene_to_shot` must exist in `scene_plan.json`.
3. Every `shot_id` must have at least one scene.
4. Every `shot_id` referenced by `scene_to_shot` must exist in `shots`.
5. `generation_mode = unique` is allowed only for the primary shot record.
6. `generation_mode = reused` must not carry an independent full prompt in phase 2+.
7. In `quality_mode = premium`, `actual_unique_shots` must equal `total_scenes`.
8. In `quality_mode = standard`, `hero` scenes must remain unique.
9. In `quality_mode = fast`, `hero` scenes must remain unique.
10. `reuse` scenes must reference a valid `source_shot_id`.

## Phase-1 Scope

Phase 1 adds:

- `visual_shot_plan.json`
- `shot_prompt_package.json`
- validator support
- adapter support back to scene-level drafts

Phase 1 does not change:

- render semantics
- FastGen generation semantics
- normalized image expectations
- final slideshow timeline model

## Planned Scripts

- `build_visual_shot_plan.py`
- `build_shot_prompt_package.py`
- `expand_shot_prompts_to_scene_drafts.py`

Phase-1 intent:

- allow experimental shot grouping
- preserve backward compatibility
- keep current project runs safe
