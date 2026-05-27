import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


BRAND_TERMS = {
    "telegram",
    "whatsapp",
    "instagram",
    "facebook",
    "youtube",
    "tiktok",
    "nike",
    "adidas",
    "apple",
    "samsung",
}

TEXT_CONFLICT_POSITIVE = {
    "readable text",
    "visible text",
    "legible text",
    "subtitles",
    "caption",
    "label text",
}

TEXT_CONFLICT_NEGATIVE = {
    "no readable text",
    "no text",
    "without readable text",
    "without text",
    "no subtitles",
}


@dataclass
class RequestSpec:
    task_type: str = "full_build"
    is_sequence: bool = True
    skip_storyboard_allowed: bool = False
    requested_format: str = "json"


@dataclass
class ValidationIssue:
    code: str
    level: str
    message: str
    target_id: str | None = None


@dataclass
class SceneMap:
    project_id: str
    source_srt_path: str
    sentence_blocks: list[dict[str, Any]]
    segment_count: int


@dataclass
class FrameBrief:
    frame_id: str
    scene_id: str
    segment_id: str
    storyboard_id: str
    shot_id: str
    semantic_unit_id: str
    visual_role: str
    shot_function: str
    source_stage: str
    timeline_in: float
    timeline_out: float
    duration_sec: float
    srt_indices: str
    srt_text: str
    scene_anchor: str
    screen_action: str
    plan: str
    camera_storyboard: str
    continuity_tags: list[str] = field(default_factory=list)
    global_style: str = ""
    hard_constraints: list[str] = field(default_factory=list)
    scale: str = "medium"
    angle: str = "eye-level"
    scene_type: str = "documentary"
    lighting: str = "motivated"
    emotional_energy: str = "steady"
    visual_density: str = "layered"
    motion_treatment: str = "static_tension"
    frame_brief_hash: str = ""
    prompt_contract_version: str = "v1"
    llm_model_id: str = "codex-gpt-5"
    llm_prompt_template_version: str = "fastgen-frame-brief-v1"
    generation_lock_version: str = "lock-v1"


@dataclass
class GenerationLockedFrame:
    frame_id: str
    image_prompt: str
    negative_prompt: str
    motion_prompt: str
    continuity_note: str
    generation_lock_status: str
    qc_risk: str
    validation_flags: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)
    frame_brief_hash: str = ""
    prompt_contract_version: str = "v1"
    llm_model_id: str = "codex-gpt-5"
    llm_prompt_template_version: str = "fastgen-frame-brief-v1"
    generation_lock_version: str = "lock-v1"


def stable_hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def normalize_text_lower(text: str) -> str:
    return normalize_text(text).lower()


def load_scene_source(project: dict) -> Path:
    final_scene_plan_path = Path(project["prompts"].get("final_scene_plan_path") or "")
    if final_scene_plan_path.exists():
        return final_scene_plan_path
    return Path(project["scene_plan"]["scene_plan_path"])


def build_frame_id(index: int) -> str:
    return f"F{index:04d}"


def build_storyboard_id(index: int) -> str:
    return f"SB{index:04d}"


def build_semantic_unit_id(index: int) -> str:
    return f"SU{index:04d}"


def build_shot_id(index: int) -> str:
    return f"SHOT{index:04d}"


def as_json_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "__dataclass_fields__"):
        return asdict(item)
    return dict(item)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def request_spec_from_project(project: dict) -> RequestSpec:
    workflow = project.get("workflow", {})
    return RequestSpec(
        task_type=str(workflow.get("task_type") or "full_build"),
        is_sequence=bool(workflow.get("is_sequence", True)),
        skip_storyboard_allowed=bool(workflow.get("skip_storyboard_allowed", False)),
        requested_format=str(workflow.get("requested_format") or "json"),
    )


def prompt_mentions_brand(prompt: str) -> bool:
    normalized = normalize_text_lower(prompt)
    return any(term in normalized for term in BRAND_TERMS)


def prompt_has_text_conflict(prompt: str) -> bool:
    normalized = normalize_text_lower(prompt)
    sanitized = normalized
    for term in TEXT_CONFLICT_NEGATIVE:
        sanitized = sanitized.replace(term, " ")
    has_positive = any(term in sanitized for term in TEXT_CONFLICT_POSITIVE)
    has_negative = any(term in normalized for term in TEXT_CONFLICT_NEGATIVE)
    return has_positive and has_negative


def prompt_restates_srt(prompt: str, srt_text: str) -> bool:
    prompt_norm = normalize_text_lower(prompt)
    srt_norm = normalize_text_lower(srt_text)
    if not srt_norm:
        return False
    if len(srt_norm) < 24:
        return srt_norm in prompt_norm
    excerpt = srt_norm[: min(len(srt_norm), 80)]
    return excerpt in prompt_norm


def is_generic_prompt(prompt: str) -> bool:
    normalized = normalize_text_lower(prompt)
    generic_markers = {
        "cinematic scene",
        "dramatic documentary image",
        "beautiful composition",
        "highly detailed documentary still",
    }
    return len(normalized) < 140 or any(marker in normalized for marker in generic_markers)


def derive_continuity_note(frame_brief: dict[str, Any]) -> str:
    continuity_tags = frame_brief.get("continuity_tags", [])
    if continuity_tags:
        return "Continuity anchors: " + ", ".join(continuity_tags)
    return "Continuity anchors: keep the same recurring world, subject family, and realism level."


def derive_motion_prompt(frame_brief: dict[str, Any]) -> str:
    motion = normalize_text(frame_brief.get("motion_treatment", "static_tension"))
    camera_storyboard = normalize_text(frame_brief.get("camera_storyboard", "documentary framing"))
    screen_action = normalize_text(frame_brief.get("screen_action", ""))
    if screen_action:
        return f"{motion}; camera behavior follows {camera_storyboard}; reveal {screen_action.lower()}."
    return f"{motion}; camera behavior follows {camera_storyboard}."


def derive_generation_block(prefix: str, image_prompt: str, negative_prompt: str) -> str:
    prompt = normalize_text(image_prompt)
    negative = normalize_text(negative_prompt)
    if negative:
        prompt = f"{prompt} Negative prompt: {negative}"
    return f"{prefix} {prompt}".strip()


def build_reference_prefix(reference_ids: list[str]) -> str:
    if not reference_ids:
        return "No character reference."
    if len(reference_ids) == 1:
        return f"Use reference image: {reference_ids[0]}."
    return f"Use reference images: {', '.join(reference_ids)}."
