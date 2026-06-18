from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_nonstop.pipeline.pilot_profiles import RuntimePilotProfile


ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"


@dataclass(frozen=True)
class RealGenerationPreflightResult:
    profile: str
    limit_frames: int
    prompt_file: str
    run_manifest_path: str
    credentials_source: str


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _fastgen_credentials_source() -> str | None:
    env_value = _clean_text(__import__("os").environ.get("FAST_GEN_API_KEY"))
    if env_value:
        return "env:FAST_GEN_API_KEY"
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("FAST_GEN_API_KEY=") and _clean_text(line.split("=", 1)[1]):
                return str(ENV_PATH)
    return None


def run_real_generation_preflight(
    *,
    project_json: Path,
    project: dict[str, Any],
    profile: RuntimePilotProfile | None,
    real_generation: bool,
    limit_frames: int | None,
) -> RealGenerationPreflightResult:
    if not project_json.exists():
        raise FileNotFoundError(f"project.json not found: {project_json}")
    if not isinstance(project, dict) or not project.get("project_id"):
        raise RuntimeError("project.json could not be loaded into a valid project payload")
    if not real_generation:
        raise RuntimeError("Real FastGen pilot requires --real-generation before any external image API call")

    generation_lock_path = Path(project.get("prompts", {}).get("generation_locked_json_path") or "")
    has_lock_based_plan = generation_lock_path.exists()

    allocation_path = Path(project["planning"]["visual_allocation_plan_path"])
    if not allocation_path.exists() and not has_lock_based_plan:
        raise FileNotFoundError(f"visual_allocation_plan is missing: {allocation_path}")

    calibration_json_path = Path(project["reports"]["visual_calibration_report_json_path"])
    if not calibration_json_path.exists() and not has_lock_based_plan:
        raise FileNotFoundError(f"visual_calibration_report is missing: {calibration_json_path}")
    calibration_payload = __import__("json").loads(calibration_json_path.read_text(encoding="utf-8")) if calibration_json_path.exists() else {}
    strict_calibration = bool(project.get("workflow", {}).get("strict_visual_calibration")) or bool(profile and profile.strict_visual_calibration)
    calibration_status = _clean_text(
        calibration_payload.get("status")
        or project.get("reports", {}).get("visual_calibration_report_status")
    ).lower()
    blocking_issues = calibration_payload.get("blocking_issues", []) if isinstance(calibration_payload, dict) else []
    if strict_calibration and (calibration_status in {"fail", "failed", "blocked"} or blocking_issues):
        raise RuntimeError("visual_calibration_report failed strict preflight; resolve blocking issues before real generation")

    prompt_file = Path(project["prompts"]["fastgen_export_path"])
    prompt_meta = prompt_file.with_suffix(prompt_file.suffix + ".meta.json")
    batches_json_path = prompt_file.with_suffix(".batches.json")
    if not prompt_file.exists() or not prompt_meta.exists():
        raise FileNotFoundError(
            f"generator-ready prompt export is missing: {prompt_file}. Build export_generation_batches before real generation."
        )
    if not batches_json_path.exists():
        raise FileNotFoundError(
            f"generation batches are missing: {batches_json_path}. Build export_generation_batches before real generation."
        )

    effective_limit = int(limit_frames or 0)
    if effective_limit <= 0:
        raise RuntimeError("A safe pilot frame cap is required. Provide --limit-frames or use a pilot profile with a default cap.")

    run_manifest_path = Path(project["images"]["run_manifest_path"])
    run_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    Path(project["images"]["raw_images_dir"]).mkdir(parents=True, exist_ok=True)

    credentials_source = _fastgen_credentials_source()
    if not credentials_source:
        raise RuntimeError("FAST_GEN_API_KEY is missing. Set it in the environment or .env before real generation.")

    return RealGenerationPreflightResult(
        profile=profile.name if profile else _clean_text(project.get("workflow", {}).get("profile") or project.get("profile_id")),
        limit_frames=effective_limit,
        prompt_file=str(prompt_file),
        run_manifest_path=str(run_manifest_path),
        credentials_source=credentials_source,
    )
