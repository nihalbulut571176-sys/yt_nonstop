# Pipeline Data Models

## Purpose

This document defines the first canonical drafts for:

- `project.json`
- `scene_plan.json`
- `publishing.json` semantics inside `project.json`
- stage statuses
- render source selection

These drafts are designed to fit the current project structure while giving us a stable target for orchestration.

## Design Principles

- One project must be resumable from structured state, not from folder memory.
- One scene record must contain enough information to drive image generation, animation, and final render.
- Existing artifacts such as `timeline.json`, FastGen manifests, and VNonStop manifests should map into this model without heavy reinterpretation.
- The schema should support both current local runs and future VPS automation.

## Canonical `project.json`

`project.json` is the top-level state object for one video project.

It answers:

- what this project is
- what its inputs are
- what stage it is in
- where all major derived artifacts live
- whether the pipeline can resume safely

### Top-level structure

```json
{
  "profile_id": "fastgen_only",
  "project_id": "telegram_darknet_001",
  "schema_version": "draft-1",
  "created_at": "2026-05-12T15:00:00Z",
  "updated_at": "2026-05-12T15:00:00Z",
  "status": "in_progress",
  "current_stage": "scene_plan",
  "meta": {},
  "inputs": {},
  "rewrite": {},
  "transcription": {},
  "scene_plan": {},
  "prompts": {},
  "images": {},
  "animation": {},
  "render": {},
  "publishing": {},
  "qc": {},
  "logs": {},
  "notes": []
}
```

### Field definitions

#### `project_id`

Stable machine-friendly identifier for the project.

Example:

```json
"project_id": "telegram_darknet_001"
```

#### `profile_id`

Execution profile for the project.

Allowed draft values:

- `veononstop`
- `fastgen_only`

#### `schema_version`

Schema version for future migrations.

#### `status`

Project-wide lifecycle status.

Allowed draft values:

- `draft`
- `ready`
- `in_progress`
- `blocked`
- `completed`
- `failed`

#### `current_stage`

Current pipeline stage.

Allowed draft values:

- `rewrite`
- `transcribe`
- `scene_plan`
- `prompt_package`
- `prompts`
- `images`
- `animation_selection`
- `video_generation`
- `mixed_cut`
- `slideshow_cut`
- `publishing_drafts`
- `thumbnail_generation`
- `qc`
- `final_render`
- `done`

#### `meta`

Human and business metadata for the project.

Suggested fields:

```json
{
  "title": "The new darknet in messengers",
  "language": "ru",
  "base_visual_language": "English",
  "target_platform": "YouTube",
  "owner": "MIKE",
  "project_root": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001"
}
```

#### `inputs`

Original user-provided assets and source material.

Suggested fields:

```json
{
  "raw_text_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\input\\raw_text.md",
  "raw_text_char_count": 3025,
  "audio_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\audio\\voiceover.mp3",
  "audio_duration_seconds": 992.392938
}
```

#### `rewrite`

State for the text rewrite stage.

Suggested fields:

```json
{
  "status": "completed",
  "master_prompt_version": "voiceover-rewrite-v1",
  "source_text_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\input\\raw_text.md",
  "rewritten_script_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\input\\voice_script.md",
  "approved_script_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\input\\voice_script_approved.md",
  "notes": "Final spoken script approved by user before recording."
}
```

#### `transcription`

State for the real-audio transcription step.

Suggested fields:

```json
{
  "status": "completed",
  "engine": "faster-whisper",
  "model": "large-v3",
  "device": "auto",
  "audio_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\audio\\voiceover.mp3",
  "srt_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\transcript\\voiceover.srt",
  "segments_json_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\transcript\\voiceover.segments.json",
  "meta_json_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\transcript\\voiceover.meta.json"
}
```

#### `scene_plan`

State for turning transcript timing into production scenes.

Suggested fields:

```json
{
  "status": "completed",
  "max_still_duration_seconds": 5,
  "source_srt_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\transcript\\voiceover.srt",
  "long_segment_report_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\scene_plan\\long_segment_report.json",
  "scene_plan_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\scene_plan\\scene_plan.json",
  "scene_count": 274,
  "original_segment_count": 188
}
```

#### `prompts`

State for visual prompt generation.

Suggested fields:

```json
{
  "status": "completed",
  "prompt_language": "English",
  "style_preset": "cinematic-realistic-v1",
  "reference_mapping_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\deliverables\\fastgen_ref_paths.json",
  "prompt_export_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\scene_plan\\scene_prompts.md",
  "prompt_package_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\prompts\\prompt_package.json",
  "generator_ready_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\prompts\\fastgen_prompts_generator_ready.md",
  "prompt_review_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\prompts\\prompt_review.md"
}
```

#### `images`

State for FastGen image generation.

Suggested fields:

```json
{
  "status": "in_progress",
  "provider": "Fast Gen",
  "route": "v4-openai-image",
  "run_manifest_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\images\\fastgen_run\\run_manifest.json",
  "raw_images_dir": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\images\\fastgen_run\\images",
  "normalized_images_dir": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\images\\normalized",
  "generated_count": 274,
  "failed_count": 0
}
```

#### `animation`

State for animation-target planning and VNonStop generation.

Suggested fields:

```json
{
  "status": "in_progress",
  "policy_name": "first_minute_then_every_third",
  "campaign_manifest_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\video_runs\\campaign_manifest.json",
  "timeline_subset_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\video_runs\\animation_target_timeline.json",
  "provider": "veononstop",
  "run_manifest_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\video_runs\\run_manifest.json",
  "videos_dir": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\video_runs\\videos",
  "success_log_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\video_runs\\success.jsonl",
  "failed_log_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\video_runs\\failed.jsonl"
}
```

#### `render`

State for mixed-cut and final render outputs.

Suggested fields:

```json
{
  "status": "pending",
  "render_strategy": "images_only",
  "mixed_manifest_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\renders\\mixed_manifest.json",
  "slideshow_timeline_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\renders\\slideshow_timeline.json",
  "ffconcat_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\renders\\timeline.ffconcat",
  "partial_outputs": [],
  "final_video_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\renders\\final.mp4"
}
```

Notes:

- `veononstop` should typically use `render_strategy = "video_if_available_else_image"`
- `fastgen_only` should use `render_strategy = "images_only"`

#### `publishing`

State for title, description, and thumbnail development.

Suggested fields:

```json
{
  "status": "pending",
  "editorial_angle": "privacy tool becoming criminal infrastructure",
  "title_generation": {
    "status": "pending",
    "prompt_version": "youtube-title-v1",
    "drafts_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\title_drafts.json",
    "approved_title_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\title_approved.txt"
  },
  "description_generation": {
    "status": "pending",
    "prompt_version": "youtube-description-v1",
    "drafts_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\description_drafts.json",
    "approved_description_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\description_approved.md"
  },
  "thumbnail_generation": {
    "status": "pending",
    "provider": "Fast Gen",
    "prompt_version": "youtube-thumbnail-v1",
    "thumbnail_brief_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\thumbnail_brief.md",
    "prompt_candidates_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\thumbnail_prompt_candidates.json",
    "approved_prompt_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\thumbnail_prompt_approved.txt",
    "run_manifest_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\thumbnails\\run_manifest.json",
    "candidates_dir": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\thumbnails\\candidates",
    "approved_thumbnail_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\publishing\\thumbnails\\approved.png"
  }
}
```

#### `qc`

Validation outputs.

Suggested fields:

```json
{
  "status": "pending",
  "qc_report_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\renders\\qc_report.json",
  "last_result": null
}
```

#### `logs`

Pipeline-level operational logs.

Suggested fields:

```json
{
  "pipeline_log_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\logs\\pipeline.log",
  "events_jsonl_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\logs\\events.jsonl"
}
```

## Canonical `scene_plan.json`

`scene_plan.json` is the canonical shot-level production plan.

It replaces ambiguous dependence on multiple partial manifests.

### File structure

Suggested structure:

```json
{
  "project_id": "telegram_darknet_001",
  "schema_version": "draft-1",
  "source_srt_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\transcript\\voiceover.srt",
  "max_still_duration_seconds": 5,
  "scene_count": 274,
  "scenes": []
}
```

### Scene object

Each record in `scenes` should describe one final timeline shot.

```json
{
  "scene_id": "scene_0001",
  "shot_index": 1,
  "source_segment_id": 1,
  "source_index": 1,
  "part_index": 1,
  "parts_total": 1,
  "start": 0.0,
  "end": 5.0,
  "duration": 5.0,
  "voice_text": "Imagine a cold night, a narrow street, a dim lamp.",
  "source_language_text": "Представьте себе холодную ночь, узкая улица, тусклый фонарь.",
  "visual_goal": "Establish the tense night setting and investigative mood.",
  "prompt": "Use reference image: CHAR_01_Journalist. cinematic realistic investigative thriller, a narrow wet night street with cracked pavement and a single weak streetlamp, cold blue-gray lighting, anxious and secretive mood, wide establishing shot, Eastern Europe or the Middle East atmosphere, no text",
  "reference_ids": ["CHAR_01_Journalist"],
  "reference_mode": "single",
  "source_kind": "original",
  "generated_index": 1,
  "still_image_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\images\\normalized\\001.png",
  "should_animate": true,
  "animation_policy_reason": "first_minute_full",
  "animation_status": "pending",
  "video_path": null,
  "render_source": "image",
  "render_asset_path": "C:\\Users\\MIKE\\Documents\\Codex\\YT\\projects\\telegram_darknet_001\\images\\normalized\\001.png",
  "notes": []
}
```

### Required scene fields

- `scene_id`
- `shot_index`
- `start`
- `end`
- `duration`
- `voice_text`
- `prompt`
- `reference_ids`
- `source_kind`
- `should_animate`
- `animation_status`
- `render_source`
- `render_asset_path`

### Recommended scene fields

- `source_segment_id`
- `source_index`
- `part_index`
- `parts_total`
- `visual_goal`
- `reference_mode`
- `generated_index`
- `still_image_path`
- `video_path`
- `animation_policy_reason`
- `notes`

## Enumerations

### `reference_mode`

- `none`
- `single`
- `multiple`

### `source_kind`

- `original`
- `extra`
- `replacement`

### `animation_status`

- `not_selected`
- `pending`
- `submitted`
- `succeeded`
- `failed`
- `skipped`

### `render_source`

- `image`
- `video`
- `missing`

## Render Source Resolution Rule

At final assembly time, render source should be resolved with this logic:

1. If `should_animate` is `true` and a valid `video_path` exists, use `render_source = "video"`.
2. Otherwise, if a valid `still_image_path` exists, use `render_source = "image"`.
3. Otherwise, mark `render_source = "missing"` and fail QC.

This preserves the current mixed-cut rule while making it explicit and machine-readable.

## Relationship To Current Files

Current files map into the canonical model like this:

- `edit/timeline.json` -> early predecessor to `scene_plan.json`
- `edit/animation_target_timeline.json` -> filtered view of scenes where `should_animate = true`
- `veononstop_run/run_manifest.json` -> provider run manifest for animated scenes
- `deliverables/.../mixed_manifest.json` -> render-specific resolved asset manifest

The long-term goal is:

- `scene_plan.json` becomes the canonical source
- all specialized manifests become derived artifacts

## Publishing Folder Recommendation

Recommended project-scoped publishing layout:

- `projects/<id>/publishing/title_drafts.json`
- `projects/<id>/publishing/title_approved.txt`
- `projects/<id>/publishing/description_drafts.json`
- `projects/<id>/publishing/description_approved.md`
- `projects/<id>/publishing/thumbnail_brief.md`
- `projects/<id>/publishing/thumbnail_prompt_candidates.json`
- `projects/<id>/publishing/thumbnail_prompt_approved.txt`
- `projects/<id>/publishing/thumbnails/run_manifest.json`
- `projects/<id>/publishing/thumbnails/candidates/`
- `projects/<id>/publishing/thumbnails/approved.png`

## Recommended Project Structure

Each new audio file should become a new isolated project under:

- `projects/<id>/project.json`
- `projects/<id>/input/`
- `projects/<id>/audio/`
- `projects/<id>/transcript/`
- `projects/<id>/scene_plan/`
- `projects/<id>/prompts/`
- `projects/<id>/images/fastgen_run/images/`
- `projects/<id>/images/normalized/`
- `projects/<id>/renders/`
- `projects/<id>/publishing/`
- `projects/<id>/logs/`

## Recommended Placement In The Pipeline

Recommended order:

For `veononstop`:

1. rewrite
2. transcribe
3. build_scene_plan
4. build_prompts
5. generate_images
6. normalize_images
7. select_animation_targets
8. generate_videos
9. build_mixed_cut
10. generate_publishing_drafts
11. generate_thumbnails
12. qc
13. final_render

For `fastgen_only`:

1. rewrite
2. transcribe
3. build_scene_plan
4. build_prompt_package
5. generate_images
6. normalize_images
7. build_slideshow_cut
8. generate_publishing_drafts
9. generate_thumbnails
10. qc
11. final_render

Editorial recommendation:

- title drafts can start right after rewrite
- description drafts can start right after rewrite and be refined after scene planning
- thumbnail prompts should usually be finalized after the narrative angle and visual direction are stable
- approved publishing assets should be stored separately from draft variants

## Minimum Implementation Strategy

To avoid overengineering the first pass:

1. Define and adopt `project.json`.
2. Define and adopt `scene_plan.json`.
3. Add publishing state inside `project.json`.
4. Make the stage graph conditional on `profile_id`.
5. Write adapters from existing `timeline.json` and manifests into these formats.
6. Keep existing generator scripts mostly unchanged at first.
7. Build orchestration around the new structured data.

## Open Decisions

These items are still intentionally open:

- whether rewritten script versions should live inside `project.json` or only as files
- whether multi-part deliveries should be represented inside `render.partial_outputs` or as separate render manifests
- whether animation campaigns need their own standalone schema or can remain derived from `scene_plan.json`

For now, the proposed model is strong enough to start implementation.
