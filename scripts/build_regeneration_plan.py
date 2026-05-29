import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_contracts import normalize_text_lower
from project_pipeline_utils import load_json, load_project, save_json, save_project


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_rows(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    rows = payload.get(key, []) if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def action_for_selection(selection: dict[str, Any], max_attempts: int) -> tuple[str, list[str]]:
    status = str(selection.get("selection_status", "")).strip()
    coverage = str(selection.get("coverage_status", "")).strip()
    flags = [str(item) for item in selection.get("semantic_flags", []) if str(item).strip()]
    reasons: list[str] = []
    if status == "reject":
        reasons.append("selected_variant_rejected")
    if status == "manual_review":
        reasons.append("manual_review_selected")
    if coverage != "pass":
        reasons.append("coverage_not_pass")
    for flag in flags:
        if flag in {"must_show_not_grounded_in_prompt", "missing_visualized_claim", "missing_must_show", "abstract_must_show", "abstract_visualized_claim"}:
            reasons.append(flag)
    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        return "accept", []
    if max_attempts <= 0:
        return "manual_review", reasons
    if any(reason in reasons for reason in {"must_show_not_grounded_in_prompt", "missing_visualized_claim", "missing_must_show", "abstract_must_show", "abstract_visualized_claim", "coverage_not_pass"}):
        return "rewrite_prompt_and_regenerate", reasons
    return "regenerate_variant", reasons


def semantic_relaxed_for_review(project: dict[str, Any], selection: dict[str, Any]) -> bool:
    qc = project.get("qc", {})
    if normalize_text_lower(qc.get("image_semantic_qc_mode")) != "disabled":
        return False
    if not bool(qc.get("allow_manual_review_without_vlm", False)):
        return False
    selection_status = normalize_text_lower(selection.get("selection_status"))
    human_review_status = normalize_text_lower(selection.get("human_review_status"))
    return selection_status == "manual_review" or human_review_status == "approve"


def prompt_rewrite_hint(selection: dict[str, Any]) -> str:
    must_show = "; ".join(str(item) for item in selection.get("must_show", []) if str(item).strip())
    claim = str(selection.get("visualized_claim", "")).strip()
    parts = []
    if claim:
        parts.append(f"Make the frame visibly prove this claim: {claim}.")
    if must_show:
        parts.append(f"The prompt must include concrete visible details for: {must_show}.")
    parts.append("Avoid abstract mood-only wording; describe objects, people, location, action, camera, and lighting.")
    return " ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    qc_path = Path(project["images"].get("image_qc_report_path", ""))
    selected_path = Path(project["images"].get("selected_images_manifest_path", ""))
    plan_path = Path(project["qc"].get("regeneration_plan_path"))

    qc_rows = load_rows(qc_path, "images")
    selected_rows = load_rows(selected_path, "selected_images")
    qc_by_scene: dict[str, list[dict[str, Any]]] = {}
    for row in qc_rows:
        qc_by_scene.setdefault(str(row.get("scene_id", "")), []).append(row)

    max_attempts = int(project.get("generation", {}).get("max_regeneration_attempts", project.get("qc", {}).get("max_regeneration_attempts", 2)) or 0)
    allow_regeneration = bool(project.get("generation", {}).get("allow_regeneration", True))
    tasks: list[dict[str, Any]] = []
    accepted = 0
    needs_action = 0

    for selection in selected_rows:
        scene_id = str(selection.get("scene_id", "")).strip()
        action, reasons = action_for_selection(selection, max_attempts if allow_regeneration else 0)
        if semantic_relaxed_for_review(project, selection):
            semantic_only_reasons = {
                "manual_review_selected",
                "coverage_not_pass",
                "must_show_not_grounded_in_prompt",
                "missing_visualized_claim",
                "missing_must_show",
                "abstract_must_show",
                "abstract_visualized_claim",
            }
            if reasons and set(reasons).issubset(semantic_only_reasons):
                action = "accept"
                reasons = []
        if action == "accept":
            accepted += 1
            continue
        needs_action += 1
        scene_qc_rows = qc_by_scene.get(scene_id, [])
        failed_variants = [
            {
                "image_id": row.get("image_id"),
                "variant_index": row.get("variant_index"),
                "variant_label": row.get("variant_label"),
                "file_path": row.get("file_path") or row.get("normalized_image_path"),
                "decision": row.get("decision"),
                "coverage_status": row.get("coverage_status"),
                "semantic_flags": row.get("semantic_flags", []),
                "score": row.get("final_score"),
            }
            for row in scene_qc_rows
            if row.get("decision") != "use" or row.get("coverage_status") != "pass"
        ]
        tasks.append(
            {
                "scene_id": scene_id,
                "beat_id": selection.get("beat_id"),
                "selected_image_id": selection.get("selected_image_id"),
                "selected_image_path": selection.get("selected_image_path"),
                "action": action,
                "reason": reasons,
                "attempt": 1,
                "max_attempts": max_attempts,
                "priority": "high" if selection.get("key_beat") or selection.get("beat_priority") == "hero" else "normal",
                "voice_text": selection.get("voice_text", ""),
                "visualized_claim": selection.get("visualized_claim", ""),
                "must_show": selection.get("must_show", []),
                "variant_count_evaluated": int(selection.get("variant_count_evaluated", 1) or 1),
                "failed_variants": failed_variants,
                "prompt_rewrite_hint": prompt_rewrite_hint(selection),
                "status": "queued" if action.startswith("rewrite") or action.startswith("regenerate") else "manual_review",
            }
        )

    payload = {
        "project_id": project.get("project_id"),
        "created_at": iso_now(),
        "mode": project.get("workflow", {}).get("profile", "custom"),
        "allow_regeneration": allow_regeneration,
        "max_attempts": max_attempts,
        "accepted_count": accepted,
        "needs_action_count": needs_action,
        "tasks": tasks,
        "notes": "Regeneration planning layer. scripts/execute_regeneration_plan.py consumes queued tasks, repairs prompt wording, regenerates target variants, reruns image QC, and leaves exhausted failures in manual_review.",
    }
    save_json(plan_path, payload)
    project.setdefault("qc", {})["regeneration_status"] = "queued" if tasks else "not_needed"
    project["qc"]["regeneration_plan_path"] = str(plan_path)
    project["current_stage"] = "execute_regeneration_plan" if tasks else "normalize_images"
    save_project(project_json, project)
    print(plan_path)


if __name__ == "__main__":
    main()
