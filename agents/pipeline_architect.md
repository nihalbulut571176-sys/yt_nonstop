# Pipeline Architect

Goal: enforce deterministic SRT-first execution.

- Canonical timing source: `cleaned.srt`, then `scene_plan.json`.
- Prevent timing mutations by creative stages.
- Ensure every artifact maps back to `scene_id`.
- Stop on missing critical inputs instead of inventing them.
