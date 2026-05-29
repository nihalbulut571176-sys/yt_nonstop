import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz
except ImportError:  # pragma: no cover - exercised through fallback path
    rapidfuzz_fuzz = None


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

FORBIDDEN_PROMPT_TERMS = {
    "subtitle",
    "subtitles",
    "caption",
    "captions",
    "watermark",
    "fake ui",
    "readable text",
    "cyrillic",
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
    beat_id: str
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
    visual_slot_id: str = ""
    source_scene_id: str = ""
    source_beat_ids: list[str] = field(default_factory=list)
    generation_decision: str = "new_image"
    slot_type: str = "story_action"
    generation_mode: str = "unique"
    source_shot_id: str = ""
    variation_note: str = ""
    shot_type: str = "medium shot"
    transition_in: str = "cut"
    transition_out: str = "cut"
    visualized_claim: str = ""
    must_show: list[str] = field(default_factory=list)
    entity_locks: list[dict[str, Any]] = field(default_factory=list)
    camera_rule: str = ""
    style_rule: str = ""
    negative_constraints: list[str] = field(default_factory=list)
    film_block_id: str = ""
    beat_priority: str = "supporting"
    key_beat: bool = False
    variant_count: int = 1
    mentioned_subject_ids: list[str] = field(default_factory=list)
    visible_subject_ids: list[str] = field(default_factory=list)
    subject_ids: list[str] = field(default_factory=list)
    primary_subject_id: str | None = None
    subject_visible: bool = False
    subject_continuity_strength: str = "none"
    reference_bindings: list[dict[str, Any]] = field(default_factory=list)
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
    beat_id: str
    scene_id: str
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


@dataclass
class V2StoryboardFrame:
    frame_id: str
    scene_id: str
    subscene_id: str
    global_scene_id: str
    start_time: str
    end_time: str
    duration_sec: float
    voice_text: str
    visual_function: str
    mini_world: str
    scene_meaning: str
    main_subject: str
    why_this_frame_exists: str
    director_prompt: dict[str, Any] = field(default_factory=dict)
    image_prompt_final: str = ""
    negative_prompt: str = ""
    dc_status: str = "pending"
    qc_flags: list[str] = field(default_factory=list)


@dataclass
class SubjectProfile:
    subject_id: str
    display_name: str
    subject_type: str
    narrative_role: str
    visual_markers: list[str] = field(default_factory=list)
    reference_policy: str = "optional"
    reference_asset_ids: list[str] = field(default_factory=list)
    continuity_prompt: str = ""
    forbidden_variation: list[str] = field(default_factory=list)


@dataclass
class ReferenceAsset:
    reference_asset_id: str
    subject_id: str
    path: str
    usage: str
    strength: str
    allowed_segments: list[str] = field(default_factory=list)


@dataclass
class ReferenceBinding:
    subject_id: str
    reference_asset_ids: list[str] = field(default_factory=list)
    usage: str = "identity_and_wardrobe"
    strength: str = "medium"


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


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text or ""))


def contains_forbidden_terms(text: str, forbidden_terms: set[str] | None = None) -> list[str]:
    normalized = normalize_text_lower(text)
    terms = forbidden_terms or FORBIDDEN_PROMPT_TERMS
    return sorted(term for term in terms if term in normalized)


def similarity_score(text_a: str, text_b: str) -> int:
    if rapidfuzz_fuzz is not None:
        return int(rapidfuzz_fuzz.token_set_ratio(text_a or "", text_b or ""))
    tokens_a = set(normalize_text_lower(text_a).split())
    tokens_b = set(normalize_text_lower(text_b).split())
    if not tokens_a and not tokens_b:
        return 100
    union = tokens_a | tokens_b
    if not union:
        return 0
    return int(round((len(tokens_a & tokens_b) / len(union)) * 100))


def prompt_length_ok(prompt: str, max_length: int = 650) -> bool:
    return len(normalize_text(prompt)) <= max_length


def count_pattern_breaks(frames: list[dict[str, Any]], seconds_window: float = 30.0) -> int:
    breaks = 0
    last_world = None
    window_start = None
    for frame in frames:
        start = float(frame.get("start", frame.get("timeline_in", 0)) or 0)
        world = normalize_text_lower(frame.get("mini_world", ""))
        if last_world is None:
            last_world = world
            window_start = start
            continue
        if world != last_world and window_start is not None and start - window_start <= seconds_window:
            breaks += 1
            window_start = start
        last_world = world
    return breaks


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = normalize_text(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result
