import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def load_list(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    rows = payload.get(key, []) if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    report_path = Path(project["qc"]["continuity_qc_report_path"])
    selected_rows = load_list(Path(project["images"].get("selected_images_manifest_path", "")), "selected_images")
    shot_plan_path = Path(project["prompts"].get("visual_shot_plan_path", ""))
    shot_plan = load_json(shot_plan_path) if shot_plan_path.exists() else {"scene_to_shot": {}, "shots": []}
    scene_to_shot = shot_plan.get("scene_to_shot", {}) if isinstance(shot_plan, dict) else {}
    shots_by_id = {item.get("shot_id"): item for item in shot_plan.get("shots", []) if item.get("shot_id")}

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    previous: dict[str, Any] | None = None
    unique_run = 0

    for index, row in enumerate(selected_rows):
        scene_id = clean(row.get("scene_id"))
        mapping = scene_to_shot.get(scene_id, {}) if isinstance(scene_to_shot, dict) else {}
        shot = shots_by_id.get(mapping.get("shot_id"), {}) if isinstance(mapping, dict) else {}
        generation_mode = clean(shot.get("generation_mode") or mapping.get("generation_mode") or row.get("generation_mode") or "unique")
        film_block_id = clean(shot.get("film_block_id") or mapping.get("film_block_id") or row.get("film_block_id"))
        transition_in = clean(shot.get("transition_in") or mapping.get("transition_in") or row.get("transition_in") or "cut")
        camera = clean(shot.get("camera"))
        lighting = clean(shot.get("lighting"))
        selection_status = clean(row.get("selection_status"))
        flags: list[str] = []

        if selection_status not in {"use", "manual_review"}:
            flags.append("non_eligible_selection")
            errors.append(f"{scene_id} has non-eligible selected image status `{selection_status}`")
        if generation_mode == "unique":
            unique_run += 1
        else:
            unique_run = 0
        if unique_run >= 5:
            flags.append("too_many_unique_shots_in_a_row")
            warnings.append(f"{scene_id} continues a long run of unique shots; consider derived/reused shot for film continuity")

        if previous:
            previous_block = clean(previous.get("film_block_id"))
            if film_block_id and previous_block and film_block_id != previous_block and transition_in in {"", "cut", "straight_cut"}:
                flags.append("film_block_jump_without_planned_transition")
                warnings.append(f"{scene_id} changes film_block from {previous_block} to {film_block_id} without an explicit transition")
            if camera and previous.get("camera") and camera != previous.get("camera") and film_block_id == previous_block:
                flags.append("camera_style_shift_within_same_block")
            if lighting and previous.get("lighting") and lighting != previous.get("lighting") and film_block_id == previous_block:
                flags.append("lighting_shift_within_same_block")

        status = "pass" if not flags else "warn"
        if "non_eligible_selection" in flags:
            status = "fail"
        check = {
            "index": index,
            "scene_id": scene_id,
            "beat_id": row.get("beat_id"),
            "selected_image_id": row.get("selected_image_id"),
            "film_block_id": film_block_id,
            "generation_mode": generation_mode,
            "transition_in": transition_in,
            "camera": camera,
            "lighting": lighting,
            "status": status,
            "flags": flags,
        }
        checks.append(check)
        previous = check

    status = "fail" if errors else "warn" if warnings else "pass"
    payload = {
        "project_id": project.get("project_id"),
        "created_at": iso_now(),
        "status": status,
        "checked_frames": len(checks),
        "warnings": list(dict.fromkeys(warnings)),
        "errors": list(dict.fromkeys(errors)),
        "checks": checks,
    }
    save_json(report_path, payload)
    project.setdefault("qc", {})["continuity_qc_status"] = status
    project["qc"]["continuity_qc_report_path"] = str(report_path)
    project["current_stage"] = "human_review"
    save_project(project_json, project)
    print(report_path)


if __name__ == "__main__":
    main()
