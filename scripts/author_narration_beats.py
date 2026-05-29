import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project
from prompt_safety import is_probably_abstract, lint_prompt_observability
from yt_nonstop.providers.llm_provider import build_json_only_prompt, complete_json, provider_from_project


ABSTRACT_ONLY_TERMS = {
    "betrayal",
    "danger",
    "truth",
    "corruption",
    "systemic failure",
    "reality",
    "logic",
    "identity",
    "network",
    "pressure",
}


def clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def humanize_token(value: str) -> str:
    cleaned = clean_text(value).replace("_", " ").replace("-", " ")
    return cleaned.strip()


def derive_spoken_claim(beat: dict, scene: dict) -> str:
    for candidate in (
        scene.get("scene_meaning"),
        scene.get("visual_goal"),
        scene.get("narrative_purpose"),
        beat.get("spoken_claim"),
        beat.get("voice_text"),
    ):
        cleaned = clean_text(candidate)
        if cleaned:
            return cleaned
    return clean_text(beat.get("voice_text", ""))


def event_must_show(scene: dict, beat: dict) -> list[str]:
    subject = humanize_token(scene.get("primary_subject") or scene.get("main_subject") or scene.get("primary_subject_id") or "")
    environment = humanize_token(scene.get("environment") or scene.get("location_id") or "")
    event_type = clean_text(scene.get("event_type") or beat.get("beat_role")).lower()
    if event_type == "assault_moment":
        return [
            "boutique attendant recoiling as irritant mist hits her face",
            "support operator partially visible near the protected display zone",
            environment or "luxury boutique interior with reflective glass cases",
        ]
    if event_type == "theft_reveal":
        return [
            "open display case with the jewel missing",
            "immediate human reaction or partial hands near the empty mount",
            environment or "luxury boutique interior with cold reflective spill",
        ]
    if event_type == "entry_moment":
        return [
            subject or "lead operator crossing the boutique entrance threshold",
            environment or "guarded boutique entrance under evening practical light",
            "camera-readable sense of arrival into a controlled luxury space",
        ]
    if event_type == "access_moment":
        return [
            "attendant opening controlled access to the protected display",
            "lock hardware and signature object readable in the same frame",
            environment or "luxury display case interior",
        ]
    return []


def fallback_must_show(scene: dict, beat: dict) -> list[str]:
    candidates = [
        scene.get("what_is_in_frame"),
        scene.get("visual_idea"),
        scene.get("primary_subject"),
        scene.get("main_subject"),
        beat.get("voice_text"),
    ]
    cleaned = []
    for item in candidates:
        value = clean_text(item)
        if value and value.lower() not in ABSTRACT_ONLY_TERMS:
            cleaned.append(value)
    environment = clean_text(scene.get("environment") or scene.get("location_id"))
    if environment:
        cleaned.append(environment)
    unique = []
    seen = set()
    for item in cleaned:
        lowered = item.lower()
        if lowered not in seen:
            unique.append(item)
            seen.add(lowered)
    return unique[:3]


def is_drawable_phrase(value: str) -> bool:
    cleaned = clean_text(value)
    if not cleaned:
        return False
    if cleaned.lower() in ABSTRACT_ONLY_TERMS:
        return False
    if is_probably_abstract(cleaned):
        return False
    warnings = lint_prompt_observability(cleaned, what_is_in_frame=cleaned)
    disqualifiers = {
        "Prompt has no observable scene description.",
        "Prompt lacks a clear physical environment.",
        "Prompt lacks a concrete observable action or state.",
        "Prompt leans abstract and may invite metaphorical substitutions.",
    }
    return not all(warning in disqualifiers for warning in warnings) or len(warnings) < 2


def derive_must_visualize(beat: dict, scene: dict) -> list[str]:
    authored_items = list(beat.get("must_visualize", []) or [])
    if authored_items:
        cleaned_authored = []
        seen = set()
        for item in authored_items:
            cleaned = clean_text(item)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            if lowered not in ABSTRACT_ONLY_TERMS:
                cleaned_authored.append(cleaned)
                seen.add(lowered)
        if cleaned_authored:
            return cleaned_authored[:3]
    items = authored_items + event_must_show(scene, beat) + fallback_must_show(scene, beat)
    filtered = []
    seen = set()
    for item in items:
        cleaned = clean_text(item)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        if is_drawable_phrase(cleaned):
            filtered.append(cleaned)
            seen.add(lowered)
    if filtered:
        return filtered[:3]

    subject = humanize_token(scene.get("primary_subject") or scene.get("main_subject") or "the same recurring documentary subject")
    environment = humanize_token(scene.get("environment") or "the same grounded documentary environment")
    action = clean_text(scene.get("visual_idea") or beat.get("voice_text") or "camera-readable investigative action")
    fallback = [
        f"{subject} in {environment}",
        f"observable physical setup showing {action}",
    ]
    return [item for item in fallback if is_drawable_phrase(item)]


def derive_entity_mentions(beat: dict, scene: dict) -> list[str]:
    values = []
    for source in (
        beat.get("entity_mentions", []),
        scene.get("subject_ids", []),
        scene.get("mentioned_subject_ids", []),
        scene.get("active_entity_ids", []),
        scene.get("visible_subject_ids", []),
    ):
        for item in source:
            cleaned = clean_text(item)
            if cleaned:
                values.append(cleaned)
    unique = []
    seen = set()
    for item in values:
        lowered = item.lower()
        if lowered not in seen:
            unique.append(item)
            seen.add(lowered)
    return unique


def derive_location_mentions(beat: dict, scene: dict) -> list[str]:
    values = [
        clean_text(scene.get("environment")),
        clean_text(scene.get("location_id")),
        clean_text(", ".join(beat.get("location_mentions", [])) if beat.get("location_mentions") else ""),
    ]
    return [item for item in values if item]


def derive_visual_priority(scene: dict, beat: dict) -> str:
    if clean_text(beat.get("visual_priority")) in {"high", "medium", "low"}:
        return clean_text(beat.get("visual_priority")).lower()
    if scene.get("event_clarity_required"):
        return "high"
    importance = clean_text(scene.get("scene_importance")).lower()
    if importance in {"hero", "key"}:
        return "high"
    if importance in {"supporting", "continuity"}:
        return "medium"
    return "low"


def derive_beat_role(scene: dict, beat: dict) -> str:
    for candidate in (
        scene.get("event_type"),
        scene.get("visual_function"),
        scene.get("shot_role"),
        beat.get("beat_role"),
    ):
        value = clean_text(candidate).lower()
        if value:
            return value.replace(" ", "_")
    return "explanation"


def normalize_authored_beat(skeleton: dict, authored: dict, scene: dict) -> dict:
    beat = dict(skeleton)
    beat["spoken_claim"] = clean_text(authored.get("spoken_claim") or derive_spoken_claim(skeleton, scene))
    beat["must_visualize"] = derive_must_visualize({**skeleton, **authored}, scene)
    beat["entity_mentions"] = derive_entity_mentions({**skeleton, **authored}, scene)
    beat["location_mentions"] = derive_location_mentions({**skeleton, **authored}, scene)
    beat["beat_role"] = derive_beat_role(scene, {**skeleton, **authored})
    beat["visual_priority"] = derive_visual_priority(scene, {**skeleton, **authored})
    return beat


def build_authoring_context(project: dict, skeleton_beats: list[dict], scene_plan: dict) -> dict:
    scenes = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", []) if scene.get("scene_id")}
    compact_beats = []
    for beat in skeleton_beats:
        scene = scenes.get(beat.get("scene_id"), {})
        compact_beats.append(
            {
                "beat_id": beat.get("beat_id"),
                "scene_id": beat.get("scene_id"),
                "start": beat.get("start"),
                "end": beat.get("end"),
                "duration": beat.get("duration"),
                "voice_text": beat.get("voice_text"),
                "scene_meaning": scene.get("scene_meaning"),
                "visual_goal": scene.get("visual_goal"),
                "what_is_in_frame": scene.get("what_is_in_frame"),
                "environment": scene.get("environment"),
                "event_type": scene.get("event_type"),
                "event_clarity_required": bool(scene.get("event_clarity_required")),
                "subject_ids": list(scene.get("subject_ids", [])),
                "active_entity_ids": list(scene.get("active_entity_ids", [])),
            }
        )
    return {
        "task": "author_narration_beats",
        "project_id": project.get("project_id"),
        "language": project.get("meta", {}).get("language"),
        "beats": compact_beats,
        "requirements": [
            "Return JSON only.",
            "Do not change beat_id, scene_id, start, end, duration, or order.",
            "For each beat, return spoken_claim, must_visualize, entity_mentions, location_mentions, beat_role, visual_priority.",
            "must_visualize items must be concrete, observable, and drawable.",
            "Do not include file paths, job ids, statuses, or runtime fields.",
        ],
    }


def authored_beats_from_payload(payload: object) -> dict[str, dict]:
    if isinstance(payload, dict):
        rows = payload.get("beats", [])
    else:
        rows = payload
    authored_rows = rows if isinstance(rows, list) else []
    result: dict[str, dict] = {}
    for item in authored_rows:
        if not isinstance(item, dict):
            continue
        scene_id = clean_text(item.get("scene_id"))
        beat_id = clean_text(item.get("beat_id"))
        key = beat_id or scene_id
        if key:
            result[key] = item
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--input-json", help="Optional authored beat JSON payload to merge over the timing skeleton.")
    parser.add_argument("--provider", default="", help="LLM provider mode override: heuristic, file, external, command, http, openai_compatible, disabled.")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    beats_path = Path(project["planning"]["narration_beats_path"])
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    if not beats_path.exists():
        raise FileNotFoundError(f"Narration beat skeleton not found: {beats_path}")

    beats_payload = load_json(beats_path)
    scene_plan = load_json(scene_plan_path)
    scene_by_id = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", []) if scene.get("scene_id")}
    provider_config = provider_from_project(
        project,
        stage_name="author_narration_beats",
        override_mode=args.provider or None,
        input_json_path=str(Path(args.input_json).resolve()) if args.input_json else None,
    )
    raw_authored: dict[str, dict] = {}
    if provider_config.mode in {"file", "command", "http", "openai_compatible"}:
        authored_payload = complete_json(
            "author_narration_beats",
            "You enrich narration beats for a silent visual pipeline. Return JSON only.",
            {
                "instruction": "Enrich the narration beats with concrete visual intent while preserving timing fields exactly.",
                "user_prompt": build_json_only_prompt(
                    instruction="Enrich the narration beats with concrete visual intent while preserving timing fields exactly.",
                    context=build_authoring_context(project, beats_payload.get("beats", []), scene_plan),
                ),
                "context": build_authoring_context(project, beats_payload.get("beats", []), scene_plan),
            },
            schema_name="narration_beats_enrichment.v1",
            required_keys=["beats"],
            provider_config=provider_config,
        )
        raw_authored = authored_beats_from_payload(authored_payload)

    authored_beats = []
    for skeleton in beats_payload.get("beats", []):
        scene = scene_by_id.get(skeleton.get("scene_id"))
        if not scene:
            continue
        authored = raw_authored.get(clean_text(skeleton.get("beat_id"))) or raw_authored.get(clean_text(skeleton.get("scene_id"))) or {}
        beat = normalize_authored_beat(skeleton, authored, scene)
        authored_beats.append(beat)

        scene["beat_id"] = beat["beat_id"]
        scene["spoken_claim"] = beat["spoken_claim"]
        scene["must_show"] = beat["must_visualize"]
        scene["visualized_claim"] = beat["spoken_claim"]
        scene["beat_priority"] = beat["visual_priority"]
        scene["beat_role"] = beat["beat_role"]

    save_json(beats_path, {"project_id": project["project_id"], "beats": authored_beats})
    save_json(scene_plan_path, scene_plan)
    project["planning"]["status"] = "narration_beats_authored"
    project["planning"]["narration_beats_status"] = "authored"
    project["current_stage"] = "build_visual_shot_plan"
    save_project(project_json, project)
    print(beats_path)


if __name__ == "__main__":
    main()
