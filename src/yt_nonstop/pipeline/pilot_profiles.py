from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CONFIGS_DIR = ROOT / "configs"


@dataclass(frozen=True)
class RuntimePilotProfile:
    name: str
    description: str
    auto_author_llm: bool | None
    render_dry_run: bool
    limit_frames: int | None
    image_retry_rounds: int | None
    image_semantic_qc_mode: str | None
    allow_real_generation: bool
    strict_visual_calibration: bool


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _profile_config_path(profile_name: str) -> Path:
    return CONFIGS_DIR / f"pipeline_profile_{profile_name}.json"


def load_profile_payload(profile_name: str) -> dict[str, Any]:
    profile_name = _clean_text(profile_name)
    if not profile_name:
        return {}
    path = _profile_config_path(profile_name)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_runtime_profile(profile_name: str) -> RuntimePilotProfile | None:
    payload = load_profile_payload(profile_name)
    if not payload:
        return None
    pilot = payload.get("pilot", {}) if isinstance(payload, dict) else {}
    return RuntimePilotProfile(
        name=_clean_text(payload.get("profile_id") or profile_name),
        description=_clean_text(payload.get("description")),
        auto_author_llm=pilot.get("auto_author_llm") if isinstance(pilot.get("auto_author_llm"), bool) else None,
        render_dry_run=bool(pilot.get("render_dry_run", False)),
        limit_frames=int(pilot.get("default_limit_frames", 0) or 0) or None,
        image_retry_rounds=int(pilot.get("default_image_retry_rounds", 0) or 0) or None,
        image_semantic_qc_mode=_clean_text(pilot.get("image_semantic_qc_mode")) or None,
        allow_real_generation=bool(pilot.get("allow_real_generation", False)),
        strict_visual_calibration=bool(pilot.get("strict_visual_calibration", False)),
    )


def active_profile_name(project: dict[str, Any], requested_profile: str | None = None) -> str:
    requested = _clean_text(requested_profile)
    if requested:
        return requested
    workflow = project.get("workflow", {})
    return (
        _clean_text(workflow.get("profile"))
        or _clean_text(project.get("profile_id"))
        or ""
    )


def effective_limit_frames(project: dict[str, Any], requested_limit: int | None, profile: RuntimePilotProfile | None) -> int | None:
    requested = int(requested_limit or 0) or None
    if requested is not None:
        return requested
    generation = project.get("generation", {})
    for candidate in (
        generation.get("max_generated_frames"),
        generation.get("pilot_limit_frames"),
        project.get("workflow", {}).get("max_generated_frames"),
    ):
        value = int(candidate or 0) if candidate is not None else 0
        if value > 0:
            return value
    return profile.limit_frames if profile else None


def apply_runtime_profile(project: dict[str, Any], args: Any) -> RuntimePilotProfile | None:
    profile_name = active_profile_name(project, getattr(args, "profile", ""))
    profile = resolve_runtime_profile(profile_name)
    if profile is None:
        return None

    args.profile = profile.name
    if profile.name == "technical_fastgen_pilot":
        args.auto_author_llm = False
    elif profile.auto_author_llm is not None:
        args.auto_author_llm = profile.auto_author_llm

    if profile.image_retry_rounds is not None:
        args.image_retry_rounds = profile.image_retry_rounds
    if profile.render_dry_run:
        args.render_dry_run = True

    project.setdefault("runtime", {})
    project["runtime"]["active_profile"] = profile.name
    project["runtime"]["profile_description"] = profile.description
    project["runtime"]["real_generation_requires_flag"] = True
    project["runtime"]["profile_render_dry_run"] = profile.render_dry_run
    if profile.limit_frames is not None:
        project["runtime"]["profile_limit_frames"] = profile.limit_frames
    if profile.image_semantic_qc_mode:
        project["runtime"]["profile_image_semantic_qc_mode"] = profile.image_semantic_qc_mode
    project.setdefault("workflow", {})["profile"] = profile.name
    if profile.strict_visual_calibration:
        project["workflow"]["strict_visual_calibration"] = True
    if profile.image_semantic_qc_mode and not project.get("qc", {}).get("image_semantic_qc_mode"):
        project.setdefault("qc", {})["image_semantic_qc_mode"] = profile.image_semantic_qc_mode
    return profile
