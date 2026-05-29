"""VLM provider boundary for image semantic QC.

The pipeline supports three semantic-QC runtime modes:

- disabled: technical image inspection only.
- heuristic: default no-VLM checks that keep local/no-API workflows running.
- external: real VLM-backed semantic QC. This mode fails fast when no provider
  is configured, so production cannot silently fall back to heuristics.

Real VLM adapters normalize provider output into the same contract consumed by
qc_generated_images.py:

- vlm_caption
- must_show_coverage, one row per requested must_show item
- identity_check
- style_continuity_check
- artifact_text_check
- voice_text_alignment_check
- coverage_status
- decision
- semantic_flags
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from yt_nonstop._paths import ensure_scripts_on_path

ensure_scripts_on_path()

from llm_pipeline_contracts import inspect_image_file
from prompt_safety import is_probably_abstract, lint_prompt_observability

try:
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover
    Image = None
    ImageFilter = None


ALLOWED_SEMANTIC_QC_MODES = {"disabled", "heuristic", "external"}
ALLOWED_VLM_PROVIDERS = {"openai", "gemini", "local"}
DEFAULT_OPENAI_VISION_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_GEMINI_VISION_MODEL = "gemini-1.5-flash"
DEFAULT_GEMINI_GENERATE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


class VLMProviderNotConfiguredError(RuntimeError):
    """Raised when external semantic QC is requested without a usable VLM."""


class ImageSemanticQCAdapter(Protocol):
    """Boundary for image-understanding providers."""

    provider_name: str

    def evaluate(
        self,
        image_path: Path,
        beat_context: dict[str, Any],
        reference_ids: list[str],
        neighbor_contexts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ...


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def normalize_mode(value: Any) -> str:
    text = clean_text(value).lower().replace("-", "_")
    aliases = {
        "off": "disabled",
        "none": "disabled",
        "no_vlm": "heuristic",
        "fallback": "heuristic",
        "local_heuristic": "heuristic",
        "vlm": "external",
        "openai": "external",
        "gemini": "external",
        "local": "external",
        "external_vlm": "external",
    }
    resolved = aliases.get(text, text or "heuristic")
    if resolved not in ALLOWED_SEMANTIC_QC_MODES:
        return resolved
    return resolved


def normalize_provider_name(value: Any) -> str:
    text = clean_text(value).lower().replace("-", "_")
    aliases = {
        "openai_vision": "openai",
        "openai_vlm": "openai",
        "gpt_vision": "openai",
        "gemini_vision": "gemini",
        "google": "gemini",
        "google_gemini": "gemini",
        "local_vlm": "local",
        "command": "local",
    }
    return aliases.get(text, text)


def image_semantic_qc_mode_from_project(project: dict[str, Any] | None = None, override: str | None = None) -> str:
    if override:
        return normalize_mode(override)
    env_value = os.environ.get("YT_NONSTOP_IMAGE_SEMANTIC_QC_MODE")
    if env_value:
        return normalize_mode(env_value)
    project = project or {}
    qc = project.get("qc", {}) if isinstance(project, dict) else {}
    images = project.get("images", {}) if isinstance(project, dict) else {}
    return normalize_mode(
        qc.get("image_semantic_qc_mode")
        or images.get("semantic_qc_mode")
        or qc.get("vlm_mode")
        or "heuristic"
    )


def image_semantic_qc_strict_from_project(project: dict[str, Any] | None = None) -> bool:
    project = project or {}
    qc = project.get("qc", {}) if isinstance(project, dict) else {}
    mode = image_semantic_qc_mode_from_project(project)
    return bool(qc.get("image_semantic_qc_strict", mode == "external"))


def image_metrics(image_path: Path) -> dict[str, Any]:
    inspection = inspect_image_file(image_path)
    metrics: dict[str, Any] = {"inspection": inspection}
    if Image is None or not inspection.get("exists"):
        return metrics
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            histogram = gray.histogram()
            total = sum(histogram) or 1
            entropy = 0.0
            for count in histogram:
                if count <= 0:
                    continue
                probability = count / total
                entropy -= probability * math.log2(probability)
            metrics["entropy"] = round(entropy, 4)
            if ImageFilter is not None:
                edges = gray.filter(ImageFilter.FIND_EDGES)
                edge_hist = edges.histogram()
                edge_total = sum(edge_hist) or 1
                edge_mean = sum(index * count for index, count in enumerate(edge_hist)) / edge_total
                metrics["edge_mean"] = round(edge_mean, 2)
    except Exception as exc:  # pragma: no cover
        metrics["error"] = str(exc)
    return metrics


def assess_prompt_semantics(beat_context: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    must_show = [clean_text(item) for item in beat_context.get("must_show", []) if clean_text(item)]
    visualized_claim = clean_text(beat_context.get("visualized_claim", ""))
    semantic_flags: list[str] = []
    coverage_rows = []
    for item in must_show:
        warnings = lint_prompt_observability(item, what_is_in_frame=item)
        status = "present"
        if is_probably_abstract(item):
            status = "uncertain"
            semantic_flags.append("abstract_must_show")
        elif len(warnings) >= 3:
            status = "uncertain"
            semantic_flags.append("weak_must_show_observability")
        coverage_rows.append({"item": item, "status": status})
    if not must_show:
        semantic_flags.append("missing_must_show")
    if not visualized_claim:
        semantic_flags.append("missing_visualized_claim")
    elif is_probably_abstract(visualized_claim):
        semantic_flags.append("abstract_visualized_claim")
    return coverage_rows, semantic_flags


def extract_json_payload(value: Any) -> Any:
    """Parse JSON returned by a provider, with fenced-code/text fallback."""
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        raise RuntimeError("VLM semantic QC provider returned empty content")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        raise RuntimeError("VLM semantic QC provider did not return JSON")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    if end <= start:
        raise RuntimeError("VLM semantic QC provider returned malformed JSON")
    return json.loads(text[start : end + 1])


def _status_from_any(value: Any, default: str = "uncertain") -> str:
    status = clean_text(value).lower().replace(" ", "_")
    aliases = {
        "ok": "pass",
        "yes": "present",
        "true": "present",
        "no": "missing",
        "false": "missing",
        "not_found": "missing",
        "partial": "partial",
        "maybe": "uncertain",
        "unknown": "uncertain",
        "not_checked": "not_checked",
    }
    return aliases.get(status, status or default)


def _coverage_lookup(rows: Any) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return lookup
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = clean_text(row.get("item") or row.get("must_show") or row.get("target"))
        if item:
            lookup[item.lower()] = row
    return lookup


def normalize_must_show_coverage(provider_rows: Any, must_show: list[str]) -> list[dict[str, Any]]:
    lookup = _coverage_lookup(provider_rows)
    normalized: list[dict[str, Any]] = []
    for item in must_show:
        row = lookup.get(item.lower(), {})
        status = _status_from_any(row.get("status") or row.get("coverage_status"), "uncertain")
        if status == "pass":
            status = "present"
        normalized.append(
            {
                "item": item,
                "status": status,
                "evidence": clean_text(row.get("evidence") or row.get("reason") or row.get("rationale")),
            }
        )
    return normalized


def _all_present(coverage_rows: list[dict[str, Any]]) -> bool:
    return bool(coverage_rows) and all(row.get("status") in {"present", "partial"} for row in coverage_rows)


def _has_missing(coverage_rows: list[dict[str, Any]]) -> bool:
    return any(row.get("status") in {"missing", "fail"} for row in coverage_rows)


def build_vlm_semantic_qc_prompt(
    *,
    beat_context: dict[str, Any],
    reference_ids: list[str],
    neighbor_contexts: list[dict[str, Any]] | None,
    visual_bible: dict[str, Any] | None = None,
) -> str:
    request = {
        "task": "image_semantic_qc",
        "checks": [
            "Describe the image in one concise vlm_caption.",
            "For every must_show item, decide whether the image visibly covers it.",
            "Check whether visible characters/persons match the provided reference_ids when references are required.",
            "Check whether style stays consistent with visual_bible / neighbor contexts.",
            "Flag extra text, subtitles, watermarks, UI text, logos, or generation artifacts.",
            "Check whether the frame fits the voice_text and visualized_claim.",
        ],
        "beat_context": beat_context,
        "reference_ids": reference_ids,
        "neighbor_contexts": neighbor_contexts or [],
        "visual_bible": visual_bible or {},
        "response_contract": {
            "format": "json",
            "required_keys": [
                "vlm_caption",
                "must_show_coverage",
                "identity_check",
                "style_continuity_check",
                "artifact_text_check",
                "voice_text_alignment_check",
                "coverage_status",
                "decision",
                "semantic_flags",
            ],
            "allowed_decisions": ["use", "manual_review", "reject"],
            "allowed_coverage_status": ["pass", "fail"],
            "must_show_coverage_row": {
                "item": "exact must_show string",
                "status": "present|partial|missing|uncertain",
                "evidence": "short visual evidence from the image",
            },
        },
    }
    return (
        "You are a strict visual semantic QC judge for a documentary image-generation pipeline. "
        "Return JSON only. Do not invent success when image evidence is unclear.\n\n"
        f"```json\n{json.dumps(request, ensure_ascii=False, indent=2)}\n```"
    )


def normalize_provider_semantic_result(
    *,
    payload: Any,
    provider_name: str,
    image_path: Path,
    beat_context: dict[str, Any],
    reference_ids: list[str],
) -> dict[str, Any]:
    parsed = extract_json_payload(payload)
    if isinstance(parsed, list):
        parsed = {"must_show_coverage": parsed}
    if not isinstance(parsed, dict):
        raise RuntimeError("VLM semantic QC provider JSON must be an object")

    must_show = [clean_text(item) for item in beat_context.get("must_show", []) if clean_text(item)]
    coverage_rows = normalize_must_show_coverage(parsed.get("must_show_coverage"), must_show)
    coverage_status = _status_from_any(parsed.get("coverage_status"), "fail")
    if coverage_status not in {"pass", "fail"}:
        coverage_status = "pass" if _all_present(coverage_rows) else "fail"

    identity_check = parsed.get("identity_check") if isinstance(parsed.get("identity_check"), dict) else {}
    if not identity_check:
        identity_check = {
            "required_reference_ids": list(reference_ids or []),
            "status": "not_required" if not reference_ids else "uncertain",
        }
    else:
        identity_check.setdefault("required_reference_ids", list(reference_ids or []))
        identity_check["status"] = _status_from_any(identity_check.get("status"), "uncertain")

    style_check = parsed.get("style_continuity_check") if isinstance(parsed.get("style_continuity_check"), dict) else {}
    style_check["status"] = _status_from_any(style_check.get("status"), "uncertain")

    artifact_check = parsed.get("artifact_text_check") if isinstance(parsed.get("artifact_text_check"), dict) else {}
    artifact_check["status"] = _status_from_any(artifact_check.get("status"), "uncertain")

    alignment_check = parsed.get("voice_text_alignment_check") if isinstance(parsed.get("voice_text_alignment_check"), dict) else {}
    alignment_check["status"] = _status_from_any(alignment_check.get("status"), "uncertain")

    semantic_flags = [clean_text(item) for item in parsed.get("semantic_flags", []) if clean_text(item)] if isinstance(parsed.get("semantic_flags"), list) else []
    if not coverage_rows:
        semantic_flags.append("missing_must_show")
    elif _has_missing(coverage_rows):
        semantic_flags.append("must_show_not_visible")
    if identity_check.get("status") in {"missing", "fail"}:
        semantic_flags.append("identity_reference_mismatch")
    if style_check.get("status") in {"missing", "fail"}:
        semantic_flags.append("style_drift")
    if artifact_check.get("status") in {"missing", "fail", "present"} and artifact_check.get("has_artifact") is True:
        semantic_flags.append("extra_text_or_artifacts")
    if alignment_check.get("status") in {"missing", "fail"}:
        semantic_flags.append("voice_text_mismatch")

    inspection = inspect_image_file(image_path)
    technical_ok = bool(inspection.get("exists") and inspection.get("readable"))
    if not technical_ok:
        semantic_flags.append("missing_image_file" if not inspection.get("exists") else "unreadable_image_file")

    decision = clean_text(parsed.get("decision") or "")
    if decision not in {"use", "manual_review", "reject"}:
        if not technical_ok or coverage_status == "fail" or any(flag in semantic_flags for flag in {"must_show_not_visible", "identity_reference_mismatch", "voice_text_mismatch"}):
            decision = "reject"
        elif semantic_flags or not _all_present(coverage_rows):
            decision = "manual_review"
        else:
            decision = "use"

    return {
        "provider": provider_name,
        "vlm_caption": clean_text(parsed.get("vlm_caption") or parsed.get("caption") or ""),
        "must_show_coverage": coverage_rows,
        "identity_check": identity_check,
        "style_continuity_check": style_check,
        "artifact_text_check": artifact_check,
        "voice_text_alignment_check": alignment_check,
        "coverage_status": "pass" if coverage_status == "pass" and technical_ok else "fail",
        "decision": "reject" if not technical_ok else decision,
        "semantic_flags": sorted(set(semantic_flags)),
        "technical_qc_passed": technical_ok,
        "vlm_required": True,
        "semantic_qc_mode": "external",
    }


class DisabledImageSemanticQCAdapter:
    """No-VLM mode that performs technical checks only."""

    provider_name = "disabled_image_semantic_qc_v1"

    def evaluate(
        self,
        image_path: Path,
        beat_context: dict[str, Any],
        reference_ids: list[str],
        neighbor_contexts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        metrics = image_metrics(image_path)
        inspection = metrics.get("inspection", {})
        technical_ok = bool(inspection.get("exists") and inspection.get("readable"))
        flags: list[str] = []
        if not inspection.get("exists"):
            flags.append("missing_image_file")
        elif not inspection.get("readable"):
            flags.append("unreadable_image_file")
        decision = "use" if technical_ok else "reject"
        return {
            "provider": self.provider_name,
            "vlm_caption": "semantic QC disabled; technical image inspection only",
            "must_show_coverage": [
                {"item": clean_text(item), "status": "not_checked", "evidence": ""}
                for item in beat_context.get("must_show", [])
                if clean_text(item)
            ],
            "identity_check": {
                "required_reference_ids": list(reference_ids or []),
                "status": "not_checked" if reference_ids else "not_required",
            },
            "style_continuity_check": {"status": "not_checked"},
            "artifact_text_check": {"status": "not_checked"},
            "voice_text_alignment_check": {"status": "not_checked"},
            "coverage_status": "pass" if technical_ok else "fail",
            "decision": decision,
            "semantic_flags": flags,
            "technical_qc_passed": technical_ok,
            "vlm_required": False,
            "semantic_qc_mode": "disabled",
        }


class HeuristicImageSemanticQCAdapter:
    """Default no-external-provider mode."""

    provider_name = "heuristic_image_semantic_qc_v1"

    def evaluate(
        self,
        image_path: Path,
        beat_context: dict[str, Any],
        reference_ids: list[str],
        neighbor_contexts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        metrics = image_metrics(image_path)
        inspection = metrics.get("inspection", {})
        must_show_coverage, semantic_flags = assess_prompt_semantics(beat_context)
        for row in must_show_coverage:
            row.setdefault("evidence", "heuristic prompt observability check")
        if not inspection.get("exists"):
            semantic_flags.append("missing_image_file")
        elif not inspection.get("readable"):
            semantic_flags.append("unreadable_image_file")
        if metrics.get("entropy") is not None and float(metrics["entropy"]) < 3.5:
            semantic_flags.append("low_visual_entropy")
        if metrics.get("edge_mean") is not None and float(metrics["edge_mean"]) < 6.0:
            semantic_flags.append("low_edge_energy")

        required_refs = list(reference_ids or [])
        identity_status = "pass" if not required_refs or inspection.get("exists") else "fail"
        if required_refs and not inspection.get("exists"):
            semantic_flags.append("missing_identity_reference_target")

        style_status = "pass"
        if neighbor_contexts:
            current_block = clean_text(beat_context.get("film_block_id", ""))
            neighbor_blocks = {clean_text(item.get("film_block_id", "")) for item in neighbor_contexts if clean_text(item.get("film_block_id", ""))}
            if current_block and neighbor_blocks and current_block not in neighbor_blocks:
                style_status = "uncertain"

        decision = "use"
        if any(flag in semantic_flags for flag in {"missing_image_file", "unreadable_image_file"}):
            decision = "reject"
        elif any(flag in semantic_flags for flag in {"abstract_must_show", "abstract_visualized_claim"}):
            decision = "manual_review"
        elif any(row["status"] != "present" for row in must_show_coverage):
            decision = "manual_review"

        return {
            "provider": self.provider_name,
            "vlm_caption": clean_text(
                f"{inspection.get('format') or 'image'} {inspection.get('width') or '?'}x{inspection.get('height') or '?'} "
                f"interpreted against beat claim: {beat_context.get('visualized_claim', '')}"
            ),
            "must_show_coverage": must_show_coverage,
            "identity_check": {
                "required_reference_ids": required_refs,
                "status": identity_status,
            },
            "style_continuity_check": {
                "status": style_status,
            },
            "artifact_text_check": {"status": "not_checked"},
            "voice_text_alignment_check": {"status": "not_checked"},
            "coverage_status": "pass" if decision in {"use", "manual_review"} and not any(flag in semantic_flags for flag in {"missing_image_file", "unreadable_image_file"}) else "fail",
            "decision": decision,
            "semantic_flags": sorted(set(semantic_flags)),
            "technical_qc_passed": bool(inspection.get("exists") and inspection.get("readable")),
            "vlm_required": False,
            "semantic_qc_mode": "heuristic",
        }


@dataclass
class VLMProviderConfig:
    provider: str
    model: str | None = None
    endpoint_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    command: str | list[str] | None = None
    timeout_seconds: float = 120.0
    temperature: float = 0.0
    max_tokens: int = 1200
    visual_bible_path: str | None = None

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        if self.provider == "openai":
            return os.environ.get("YT_NONSTOP_OPENAI_VISION_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if self.provider == "gemini":
            return os.environ.get("YT_NONSTOP_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        return os.environ.get("YT_NONSTOP_VLM_API_KEY")


def _float_from_any(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_from_any(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _raw_vlm_config(project: dict[str, Any]) -> dict[str, Any]:
    qc = project.get("qc", {}) if isinstance(project, dict) else {}
    raw = qc.get("vlm_semantic_qc") or qc.get("image_semantic_qc_vlm") or qc.get("vlm_provider") or {}
    return raw if isinstance(raw, dict) else {}


def vlm_config_from_project(project: dict[str, Any] | None = None) -> VLMProviderConfig:
    project = project or {}
    qc = project.get("qc", {}) if isinstance(project, dict) else {}
    raw = _raw_vlm_config(project)
    provider = normalize_provider_name(
        os.environ.get("YT_NONSTOP_VLM_PROVIDER")
        or raw.get("provider")
        or qc.get("image_semantic_qc_provider")
        or ""
    )
    if not provider or provider in {"external", "vlm", "heuristic", "disabled", "none"}:
        raise VLMProviderNotConfiguredError(
            "External VLM semantic QC requires a real provider: set qc.image_semantic_qc_provider "
            "or YT_NONSTOP_VLM_PROVIDER to one of: openai, gemini, local."
        )
    if provider not in ALLOWED_VLM_PROVIDERS:
        allowed = ", ".join(sorted(ALLOWED_VLM_PROVIDERS))
        raise VLMProviderNotConfiguredError(f"Unsupported VLM semantic QC provider `{provider}`. Allowed: {allowed}")

    provider_raw = raw.get(provider, {}) if isinstance(raw.get(provider), dict) else {}
    merged = {**raw, **provider_raw}
    return VLMProviderConfig(
        provider=provider,
        model=os.environ.get("YT_NONSTOP_VLM_MODEL") or merged.get("model"),
        endpoint_url=os.environ.get("YT_NONSTOP_VLM_URL") or merged.get("endpoint_url") or merged.get("url"),
        api_key=os.environ.get("YT_NONSTOP_VLM_API_KEY") or merged.get("api_key"),
        api_key_env=os.environ.get("YT_NONSTOP_VLM_API_KEY_ENV") or merged.get("api_key_env"),
        command=os.environ.get("YT_NONSTOP_LOCAL_VLM_CMD") or merged.get("command"),
        timeout_seconds=_float_from_any(os.environ.get("YT_NONSTOP_VLM_TIMEOUT_SECONDS") or merged.get("timeout_seconds"), 120.0),
        temperature=_float_from_any(os.environ.get("YT_NONSTOP_VLM_TEMPERATURE") or merged.get("temperature"), 0.0),
        max_tokens=_int_from_any(os.environ.get("YT_NONSTOP_VLM_MAX_TOKENS") or merged.get("max_tokens"), 1200),
        visual_bible_path=os.environ.get("YT_NONSTOP_VISUAL_BIBLE_PATH") or merged.get("visual_bible_path") or project.get("prompts", {}).get("visual_bible_path"),
    )


def _load_visual_bible(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _image_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def _inline_image_payload(image_path: Path) -> tuple[str, str]:
    suffix = image_path.suffix.lower().lstrip(".") or "png"
    mime = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return mime, encoded


class BaseExternalVLMAdapter:
    provider_name = "external_vlm_semantic_qc_base"

    def __init__(self, project: dict[str, Any] | None = None, config: VLMProviderConfig | None = None) -> None:
        self.project = project or {}
        self.config = config or vlm_config_from_project(self.project)
        self.visual_bible = _load_visual_bible(self.config.visual_bible_path)
        self.validate_configuration()

    def validate_configuration(self) -> None:
        raise NotImplementedError

    def call_provider(self, *, image_path: Path, prompt: str) -> Any:
        raise NotImplementedError

    def evaluate(
        self,
        image_path: Path,
        beat_context: dict[str, Any],
        reference_ids: list[str],
        neighbor_contexts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        inspection = inspect_image_file(image_path)
        if not inspection.get("exists") or not inspection.get("readable"):
            return normalize_provider_semantic_result(
                payload={
                    "vlm_caption": "image file is missing or unreadable",
                    "must_show_coverage": [
                        {"item": clean_text(item), "status": "missing", "evidence": "image file was not available"}
                        for item in beat_context.get("must_show", [])
                        if clean_text(item)
                    ],
                    "coverage_status": "fail",
                    "decision": "reject",
                    "semantic_flags": ["missing_image_file" if not inspection.get("exists") else "unreadable_image_file"],
                },
                provider_name=self.provider_name,
                image_path=image_path,
                beat_context=beat_context,
                reference_ids=reference_ids,
            )
        prompt = build_vlm_semantic_qc_prompt(
            beat_context=beat_context,
            reference_ids=reference_ids,
            neighbor_contexts=neighbor_contexts,
            visual_bible=self.visual_bible,
        )
        payload = self.call_provider(image_path=image_path, prompt=prompt)
        return normalize_provider_semantic_result(
            payload=payload,
            provider_name=self.provider_name,
            image_path=image_path,
            beat_context=beat_context,
            reference_ids=reference_ids,
        )

    def _post_json(self, url: str, payload: dict[str, Any], bearer_token: str | None = None) -> Any:
        headers = {"Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.provider_name} failed {exc.code}: {body}") from exc
        return extract_json_payload(text)


class OpenAIVisionSemanticQCAdapter(BaseExternalVLMAdapter):
    provider_name = "openai_vision_semantic_qc_v1"

    def validate_configuration(self) -> None:
        if self.config.provider != "openai":
            raise VLMProviderNotConfiguredError("OpenAIVisionSemanticQCAdapter requires provider='openai'")
        if not self.config.resolved_api_key:
            raise VLMProviderNotConfiguredError(
                "OpenAI vision semantic QC requires OPENAI_API_KEY, YT_NONSTOP_OPENAI_VISION_API_KEY, "
                "YT_NONSTOP_VLM_API_KEY, or qc.vlm_semantic_qc.openai.api_key_env."
            )
        self.config.model = self.config.model or DEFAULT_OPENAI_VISION_MODEL
        self.config.endpoint_url = self.config.endpoint_url or DEFAULT_OPENAI_RESPONSES_URL

    def call_provider(self, *, image_path: Path, prompt: str) -> Any:
        body = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_tokens,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": _image_data_url(image_path)},
                    ],
                }
            ],
        }
        response = self._post_json(self.config.endpoint_url or DEFAULT_OPENAI_RESPONSES_URL, body, bearer_token=self.config.resolved_api_key)
        if isinstance(response, dict):
            if response.get("output_text"):
                return extract_json_payload(response["output_text"])
            output = response.get("output") or []
            for item in output:
                if not isinstance(item, dict):
                    continue
                for content_item in item.get("content", []) or []:
                    if isinstance(content_item, dict) and content_item.get("text"):
                        return extract_json_payload(content_item["text"])
        return response


class GeminiVisionSemanticQCAdapter(BaseExternalVLMAdapter):
    provider_name = "gemini_vision_semantic_qc_v1"

    def validate_configuration(self) -> None:
        if self.config.provider != "gemini":
            raise VLMProviderNotConfiguredError("GeminiVisionSemanticQCAdapter requires provider='gemini'")
        if not self.config.resolved_api_key:
            raise VLMProviderNotConfiguredError(
                "Gemini vision semantic QC requires YT_NONSTOP_GEMINI_API_KEY, GEMINI_API_KEY, "
                "GOOGLE_API_KEY, YT_NONSTOP_VLM_API_KEY, or qc.vlm_semantic_qc.gemini.api_key_env."
            )
        self.config.model = self.config.model or DEFAULT_GEMINI_VISION_MODEL
        if not self.config.endpoint_url:
            self.config.endpoint_url = DEFAULT_GEMINI_GENERATE_URL_TEMPLATE.format(
                model=self.config.model,
                api_key=self.config.resolved_api_key,
            )

    def call_provider(self, *, image_path: Path, prompt: str) -> Any:
        mime_type, encoded = _inline_image_payload(image_path)
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inlineData": {"mimeType": mime_type, "data": encoded}},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        response = self._post_json(self.config.endpoint_url or "", body)
        if isinstance(response, dict):
            candidates = response.get("candidates") or []
            for candidate in candidates:
                content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
                parts = content.get("parts", []) if isinstance(content, dict) else []
                for part in parts:
                    if isinstance(part, dict) and part.get("text"):
                        return extract_json_payload(part["text"])
        return response


class LocalVLMAdapter(BaseExternalVLMAdapter):
    """Local/command VLM adapter.

    The command receives JSON on stdin and must write the normalized semantic-QC
    JSON contract to stdout. This keeps local Ollama/LM Studio/custom services
    outside the core pipeline and avoids adding runtime dependencies here.
    """

    provider_name = "local_vlm_semantic_qc_v1"

    def validate_configuration(self) -> None:
        if self.config.provider != "local":
            raise VLMProviderNotConfiguredError("LocalVLMAdapter requires provider='local'")
        if not self.config.command and not self.config.endpoint_url:
            raise VLMProviderNotConfiguredError(
                "Local VLM semantic QC requires YT_NONSTOP_LOCAL_VLM_CMD, YT_NONSTOP_VLM_URL, "
                "qc.vlm_semantic_qc.local.command, or qc.vlm_semantic_qc.local.endpoint_url."
            )

    def call_provider(self, *, image_path: Path, prompt: str) -> Any:
        request_payload = {
            "task": "image_semantic_qc",
            "prompt": prompt,
            "image_path": str(image_path),
            "image_base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
            "response_contract": "vlm_caption + must_show_coverage + identity/style/artifact/voice checks",
        }
        if self.config.command:
            argv = self.config.command if isinstance(self.config.command, list) else shlex.split(str(self.config.command))
            if not argv:
                raise VLMProviderNotConfiguredError("Local VLM command is empty")
            completed = subprocess.run(
                argv,
                input=json.dumps(request_payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"local VLM command failed with exit code {completed.returncode}: {completed.stderr.strip()}"
                )
            return extract_json_payload(completed.stdout)
        return self._post_json(self.config.endpoint_url or "", request_payload, bearer_token=self.config.resolved_api_key)


class ExternalVLMImageSemanticQCAdapter(BaseExternalVLMAdapter):
    """Compatibility alias that dispatches to the configured real VLM adapter."""

    provider_name = "external_vlm_image_semantic_qc_dispatcher"

    def __init__(self, project: dict[str, Any] | None = None, provider: str | None = None, config: VLMProviderConfig | None = None) -> None:
        project = project or {}
        if config is None:
            if provider:
                project = dict(project)
                project.setdefault("qc", {})["image_semantic_qc_provider"] = provider
            config = vlm_config_from_project(project)
        if config.provider == "openai":
            self.delegate = OpenAIVisionSemanticQCAdapter(project=project, config=config)
        elif config.provider == "gemini":
            self.delegate = GeminiVisionSemanticQCAdapter(project=project, config=config)
        elif config.provider == "local":
            self.delegate = LocalVLMAdapter(project=project, config=config)
        else:  # pragma: no cover - vlm_config_from_project validates this first
            raise VLMProviderNotConfiguredError(f"Unsupported VLM provider `{config.provider}`")
        self.provider_name = self.delegate.provider_name

    def validate_configuration(self) -> None:  # pragma: no cover - delegate validates in __init__
        return None

    def call_provider(self, *, image_path: Path, prompt: str) -> Any:  # pragma: no cover
        return self.delegate.call_provider(image_path=image_path, prompt=prompt)

    def evaluate(
        self,
        image_path: Path,
        beat_context: dict[str, Any],
        reference_ids: list[str],
        neighbor_contexts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.delegate.evaluate(
            image_path=image_path,
            beat_context=beat_context,
            reference_ids=reference_ids,
            neighbor_contexts=neighbor_contexts,
        )


def default_image_semantic_qc_adapter(project: dict[str, Any] | None = None, mode: str | None = None) -> ImageSemanticQCAdapter:
    resolved = image_semantic_qc_mode_from_project(project, mode)
    if resolved == "disabled":
        return DisabledImageSemanticQCAdapter()
    if resolved == "heuristic":
        return HeuristicImageSemanticQCAdapter()
    if resolved == "external":
        return ExternalVLMImageSemanticQCAdapter(project=project or {})
    raise ValueError(f"Unsupported image semantic QC mode: {resolved}")
