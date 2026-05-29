from __future__ import annotations

from typing import Any


VALID_MOTION_TYPES = {
    "static_hold",
    "slow_push_in",
    "subtle_push_in",
    "slight_push",
    "slow_pan",
    "slow_pan_left",
    "slow_pan_right",
    "slow_pull_out",
}

VALID_MOTION_INTENSITIES = {"none", "low", "medium", "high"}
VALID_CROP_ANCHORS = {"center", "left", "right", "top", "bottom", "top_left", "top_right", "bottom_left", "bottom_right"}
VALID_TRANSITION_STYLES = {"hard_cut", "planned_transition", "soft_cut"}


_DETAIL_MARKERS = {"detail", "insert", "evidence", "document", "receipt", "object", "macro"}
_REACTION_MARKERS = {"reaction", "emotion", "aftermath", "face", "portrait"}
_ESTABLISHING_MARKERS = {"establishing", "location", "wide", "opening", "set_location"}
_REVEAL_MARKERS = {"reveal", "discovery", "twist", "missing", "expose"}
_ACTION_MARKERS = {"action", "movement", "enter", "exit", "follow", "chase", "walk", "route"}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _contains_any(text: str, markers: set[str]) -> bool:
    haystack = text.lower()
    return any(marker in haystack for marker in markers)


def _explicit(value: Any, allowed: set[str], fallback: str) -> str:
    text = clean_text(value).lower()
    return text if text in allowed else fallback


def derive_motion_metadata(scene: dict[str, Any], previous_scene: dict[str, Any] | None = None) -> dict[str, str]:
    """Derive a conservative cinematic motion plan for a timeline/EDL row.

    This function is deterministic on purpose: LLM/shot planning may provide explicit
    motion fields, but Python owns the final bounded values that the renderer can
    safely execute without changing timing.
    """
    explicit_motion = clean_text(scene.get("motion_type") or scene.get("motion_id") or scene.get("motion_treatment")).lower()
    explicit_intensity = clean_text(scene.get("motion_intensity")).lower()
    explicit_anchor = clean_text(scene.get("crop_anchor")).lower()
    explicit_transition = clean_text(scene.get("transition_style")).lower()

    slot_type = clean_text(scene.get("slot_type")).lower()
    visual_function = clean_text(scene.get("visual_function") or scene.get("shot_function") or scene.get("visual_role")).lower()
    shot_type = clean_text(scene.get("shot_type")).lower()
    decision = clean_text(scene.get("generation_decision") or scene.get("generation_mode")).lower()
    text = " ".join([slot_type, visual_function, shot_type, decision, clean_text(scene.get("visualized_claim")).lower()])

    previous_film_block = clean_text((previous_scene or {}).get("film_block_id"))
    current_film_block = clean_text(scene.get("film_block_id"))
    film_block_changed = bool(previous_scene and current_film_block and previous_film_block and current_film_block != previous_film_block)

    if explicit_motion in VALID_MOTION_TYPES:
        motion_type = explicit_motion
    elif slot_type == "establishing_shot":
        motion_type = "slow_pan"
    elif decision in {"hold_previous", "continuation_motion"}:
        motion_type = "subtle_push_in"
    elif _contains_any(text, _DETAIL_MARKERS):
        motion_type = "static_hold"
    elif _contains_any(text, _REACTION_MARKERS):
        motion_type = "subtle_push_in"
    elif _contains_any(text, _ESTABLISHING_MARKERS):
        motion_type = "slow_pan"
    elif _contains_any(text, _REVEAL_MARKERS):
        motion_type = "slow_push_in"
    elif _contains_any(text, _ACTION_MARKERS):
        motion_type = "slow_push_in"
    else:
        motion_type = "slow_push_in"

    if explicit_intensity in VALID_MOTION_INTENSITIES:
        motion_intensity = explicit_intensity
    elif motion_type == "static_hold":
        motion_intensity = "none"
    elif motion_type in {"subtle_push_in", "slight_push"}:
        motion_intensity = "low"
    elif motion_type == "slow_pan":
        motion_intensity = "low"
    else:
        motion_intensity = "low"

    if explicit_anchor in VALID_CROP_ANCHORS:
        crop_anchor = explicit_anchor
    elif _contains_any(text, _DETAIL_MARKERS):
        crop_anchor = "center"
    elif _contains_any(text, _ESTABLISHING_MARKERS):
        crop_anchor = "center"
    elif _contains_any(text, _ACTION_MARKERS):
        crop_anchor = "center"
    else:
        crop_anchor = "center"

    if explicit_transition in VALID_TRANSITION_STYLES:
        transition_style = explicit_transition
    elif film_block_changed:
        transition_style = "planned_transition"
    elif _contains_any(text, _ACTION_MARKERS):
        transition_style = "hard_cut"
    else:
        transition_style = "hard_cut"

    return {
        "motion_type": motion_type,
        "motion_intensity": motion_intensity,
        "crop_anchor": crop_anchor,
        "transition_style": transition_style,
    }
