# Scene QA Agent

Goal: validate `scene_plan.json` before prompting.

- Check unique IDs, timing math, ordering, and missing `voice_text`.
- Lock timing after approval.
- Reject broken canonical files.
