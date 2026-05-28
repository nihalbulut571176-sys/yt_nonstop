import re
import urllib.error
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_contracts import stable_hash

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow may be unavailable in some environments
    Image = None


REQUIRED_SCENE_DRAFT_FIELDS = ("scene_id", "frame_id", "beat_id", "visual_goal", "visualized_claim", "final_prompt")
RECOMMENDED_SCENE_DRAFT_FIELDS = (
    "shot_role",
    "primary_subject",
    "secondary_subjects",
    "what_is_in_frame",
    "camera",
    "composition",
    "lighting",
    "mood",
    "continuity_notes",
    "negative_prompt",
    "must_not_show",
    "event_clarity_required",
    "event_type",
)
FORBIDDEN_SCENE_DRAFT_FIELDS = {
    "start",
    "end",
    "duration",
    "scene_order",
    "current_stage",
    "status",
    "job_id",
    "created_at",
    "image_path",
    "still_image_path",
    "render_asset_path",
    "output_file",
    "error_type",
    "error_message",
}
REQUIRED_VISUAL_BIBLE_FIELDS = (
    "project_id",
    "main_subject",
    "subject_type",
    "visual_world",
    "continuity_rules",
)
TECHNICAL_ERROR_TYPES = {
    "policy_violation",
    "timeout",
    "network_error",
    "filesystem_error",
    "invalid_image",
    "runtime_error",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_generation_job_id(project_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "-", str(project_id or "job").lower()).strip("-") or "job"
    return f"{slug}-{stamp}-{uuid.uuid4().hex[:8]}"


def compute_prompt_hash(prompt: str, refs: list[str] | None = None, settings: dict[str, Any] | None = None) -> str:
    payload = {
        "prompt": str(prompt or ""),
        "refs": list(refs or []),
        "settings": settings or {},
    }
    return stable_hash(payload)


def _has_forbidden_runtime_field(key: str) -> bool:
    return key in FORBIDDEN_SCENE_DRAFT_FIELDS or key.endswith("_path") or key.endswith("_status")


def validate_visual_bible_payload(payload: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return ["visual_bible must be a JSON object"], warnings
    for field in REQUIRED_VISUAL_BIBLE_FIELDS:
        value = payload.get(field)
        if isinstance(value, list):
            if not value:
                errors.append(f"visual_bible missing required field `{field}`")
        elif not str(value or "").strip():
            errors.append(f"visual_bible missing required field `{field}`")
    return errors, warnings


def validate_scene_prompt_drafts_payload(payload: Any, expected_scene_ids: list[str] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, list) or not payload:
        return ["llm_prompt_drafts is empty or not a JSON array"], warnings

    seen_scene_ids: set[str] = set()
    expected_set = set(expected_scene_ids or [])
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            errors.append(f"Draft record #{index} is not a JSON object")
            continue
        scene_id = str(record.get("scene_id", "")).strip()
        label = scene_id or f"<record_{index}>"
        if not scene_id:
            errors.append(f"{label} missing required field `scene_id`")
        elif scene_id in seen_scene_ids:
            errors.append(f"Duplicate draft record for {scene_id}")
        else:
            seen_scene_ids.add(scene_id)

        forbidden = sorted(key for key in record if _has_forbidden_runtime_field(key))
        if forbidden:
            errors.append(f"{label} contains Python-owned fields: {', '.join(forbidden)}")

        for field in REQUIRED_SCENE_DRAFT_FIELDS:
            if not str(record.get(field, "")).strip():
                errors.append(f"{label} missing required field `{field}`")

        if record.get("active_entity_ids") and not record.get("continuity_cast"):
            warnings.append(f"{label} has active entities but no continuity_cast")

        missing_recommended = [
            field
            for field in RECOMMENDED_SCENE_DRAFT_FIELDS
            if field not in record or (isinstance(record[field], str) and not record[field].strip())
        ]
        if len(missing_recommended) >= 6:
            warnings.append(f"{label} is sparse on recommended creative fields")

    if expected_set:
        missing = sorted(expected_set - seen_scene_ids)
        extra = sorted(seen_scene_ids - expected_set)
        if missing:
            errors.append(f"Missing LLM prompt drafts for {len(missing)} scenes")
        if extra:
            errors.append(f"Unexpected LLM prompt drafts for {len(extra)} scenes")
    return errors, warnings


def classify_generation_error(error: Exception | str) -> str:
    message = str(error).lower()
    if any(
        marker in message
        for marker in (
            "content polic",
            "may violate our content policies",
            "guardrails around violence",
            "rejected by openai content policy",
        )
    ):
        return "policy_violation"
    if isinstance(error, TimeoutError) or "timed out" in message or "timeout" in message:
        return "timeout"
    if isinstance(error, (urllib.error.HTTPError, urllib.error.URLError)):
        return "network_error"
    if any(marker in message for marker in ("connection", "dns", "network", "http error", "urlopen")):
        return "network_error"
    if any(marker in message for marker in ("file not found", "no such file", "missing file", "unexpected result format")):
        return "filesystem_error"
    if any(marker in message for marker in ("cannot identify image file", "invalid image", "truncated image")):
        return "invalid_image"
    return "runtime_error"


def inspect_image_file(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "exists": path.exists(),
        "readable": False,
        "format": None,
        "width": None,
        "height": None,
    }
    if not path.exists():
        return info
    try:
        if Image is not None:
            with Image.open(path) as image:
                image.load()
                info["readable"] = True
                info["format"] = image.format
                info["width"], info["height"] = image.size
                return info
    except Exception as exc:  # pragma: no cover - exact PIL failure varies
        info["error"] = str(exc)
        return info

    signature = path.read_bytes()[:16]
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        info["readable"] = True
        info["format"] = "PNG"
    elif signature.startswith(b"\xff\xd8\xff"):
        info["readable"] = True
        info["format"] = "JPEG"
    elif signature[:4] == b"RIFF" and signature[8:12] == b"WEBP":
        info["readable"] = True
        info["format"] = "WEBP"
    return info


def validate_generation_manifest(manifest: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(manifest, dict):
        return ["Image manifest must be a JSON object"], warnings

    records = manifest.get("generated_images", [])
    if not isinstance(records, list) or not records:
        return ["Image manifest contains no generated image records"], warnings

    if not str(manifest.get("job_id", "")).strip():
        errors.append("Image manifest missing job_id")

    for record in records:
        label = str(record.get("scene_id") or record.get("output_file") or "<unknown>")
        for field in ("job_id", "scene_id", "source_prompt_index", "prompt_hash", "generator_profile", "created_at", "status"):
            if not str(record.get(field, "")).strip():
                errors.append(f"{label} missing image manifest field `{field}`")
        status = str(record.get("status", "")).strip()
        if status == "success":
            image_path = record.get("image_path")
            if not image_path:
                errors.append(f"{label} success record missing image_path")
                continue
            inspection = inspect_image_file(Path(image_path))
            if not inspection["exists"]:
                errors.append(f"{label} marked success but image file is missing")
            elif not inspection["readable"]:
                errors.append(f"{label} image file is not readable")
        elif status in {"failed", "missing"} and not str(record.get("error_type", "")).strip():
            warnings.append(f"{label} missing error_type for non-success status")

        error_type = str(record.get("error_type", "")).strip()
        if error_type and error_type not in TECHNICAL_ERROR_TYPES:
            warnings.append(f"{label} uses unknown error_type `{error_type}`")

    failed_count = int(manifest.get("failed_count", 0) or 0)
    if failed_count > 0:
        warnings.append(f"Image generation recorded {failed_count} failed scenes")
    return errors, warnings
