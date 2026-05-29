import argparse
import base64
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9uoAAAAASUVORK5CYII="
)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def copy_or_write_png(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.exists():
        shutil.copyfile(source_path, target_path)
    else:
        target_path.write_bytes(TINY_PNG)


def load_rows(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    rows = payload.get(key, []) if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def save_rows(path: Path, key: str, rows: list[dict[str, Any]], *, project_id: str) -> None:
    save_json(path, {"project_id": project_id, "updated_at": iso_now(), key: rows})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--mode", choices=["fake"], default="fake")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    project_root = Path(project["meta"]["project_root"])
    plan_path = Path(project["qc"]["regeneration_plan_path"])
    selected_path = Path(project["images"]["selected_images_manifest_path"])
    qc_report_path = Path(project["images"]["image_qc_report_path"])
    prompts_path = Path(project["prompts"]["llm_prompt_drafts_path"])
    report_path = Path(project["qc"]["regeneration_execution_report_path"])
    images_dir = Path(project["images"]["raw_images_dir"])

    plan = load_json(plan_path)
    tasks = plan.get("tasks", []) if isinstance(plan, dict) else []
    selected_rows = load_rows(selected_path, "selected_images")
    qc_rows = load_rows(qc_report_path, "images")
    prompt_rows = load_json(prompts_path) if prompts_path.exists() else []
    selected_by_scene = {str(row.get("scene_id", "")).strip(): row for row in selected_rows if str(row.get("scene_id", "")).strip()}
    prompt_by_scene = {str(row.get("scene_id", "")).strip(): row for row in prompt_rows if isinstance(row, dict) and str(row.get("scene_id", "")).strip()}

    attempts: list[dict[str, Any]] = []
    completed = 0
    for task in tasks:
        if str(task.get("status", "")).strip() not in {"queued", "pending", "manual_review"}:
            continue
        scene_id = str(task.get("scene_id", "")).strip()
        selected = selected_by_scene.get(scene_id)
        if not selected:
            continue
        attempt_index = len(task.get("attempts", []) or []) + 1
        source_path = Path(str(selected.get("selected_image_path") or selected.get("normalized_image_path") or ""))
        regenerated_path = images_dir / f"{scene_id}_regen_A{attempt_index:02d}.png"
        copy_or_write_png(source_path, regenerated_path)
        if scene_id in prompt_by_scene:
            prompt_row = prompt_by_scene[scene_id]
            prompt_row["final_prompt"] = (
                str(prompt_row.get("final_prompt") or "").strip()
                + " Repaired prompt wording after failed semantic coverage; keep the same timing and continuity."
            ).strip()
            prompt_row["repair_status"] = "repaired_by_fake_regeneration"
        selected["selected_image_path"] = str(regenerated_path)
        selected["normalized_image_path"] = str(regenerated_path)
        selected["selection_status"] = "use"
        selected["coverage_status"] = "pass"
        selected["semantic_flags"] = []
        selected["regeneration_attempts"] = list(selected.get("regeneration_attempts", [])) + [
            {
                "attempt": attempt_index,
                "mode": args.mode,
                "image_path": str(regenerated_path),
                "completed_at": iso_now(),
            }
        ]
        qc_rows.append(
            {
                "image_id": f"{scene_id}_regen_A{attempt_index:02d}",
                "scene_id": scene_id,
                "beat_id": task.get("beat_id"),
                "variant_index": int(selected.get("variant_count_evaluated", 1) or 1) + attempt_index,
                "variant_label": f"RA{attempt_index:02d}",
                "file_path": str(regenerated_path),
                "normalized_image_path": str(regenerated_path),
                "voice_text": selected.get("voice_text", ""),
                "visualized_claim": selected.get("visualized_claim", ""),
                "must_show": selected.get("must_show", []),
                "prompt_semantic_status": "pass",
                "prompt_semantic_flags": [],
                "vlm_caption": "fake regenerated image",
                "must_show_coverage": [{"item": item, "status": "present"} for item in selected.get("must_show", [])],
                "identity_check": {"status": "pass"},
                "style_continuity_check": {"status": "pass"},
                "artifact_text_check": {"status": "pass"},
                "voice_text_alignment_check": {"status": "pass"},
                "semantic_qc_provider": "fake_regeneration_executor",
                "vlm_required": False,
                "technical_qc_passed": True,
                "coverage_status": "pass",
                "semantic_flags": [],
                "decision": "use",
                "final_score": 8.5,
            }
        )
        task_attempt = {
            "attempt": attempt_index,
            "mode": args.mode,
            "started_at": iso_now(),
            "finished_at": iso_now(),
            "result_image_path": str(regenerated_path),
            "result": "completed",
        }
        task["attempts"] = list(task.get("attempts", [])) + [task_attempt]
        task["status"] = "completed"
        task["completed_at"] = iso_now()
        task["result_image_path"] = str(regenerated_path)
        attempts.append({"scene_id": scene_id, **task_attempt})
        completed += 1

    save_rows(selected_path, "selected_images", selected_rows, project_id=str(project.get("project_id", "")))
    save_rows(qc_report_path, "images", qc_rows, project_id=str(project.get("project_id", "")))
    if prompts_path.exists():
        save_json(prompts_path, prompt_rows)
    plan["tasks"] = tasks
    plan["executed_at"] = iso_now()
    plan["execution_mode"] = args.mode
    save_json(plan_path, plan)
    execution_report = {
        "project_id": project.get("project_id"),
        "executed_at": iso_now(),
        "mode": args.mode,
        "attempt_count": len(attempts),
        "completed_task_count": completed,
        "attempts": attempts,
    }
    save_json(report_path, execution_report)
    project.setdefault("qc", {})["regeneration_status"] = "completed" if completed else "not_needed"
    project["qc"]["regeneration_execution_report_path"] = str(report_path)
    project["current_stage"] = "build_continuity_qc"
    save_project(project_json, project)
    print(report_path)


if __name__ == "__main__":
    main()
