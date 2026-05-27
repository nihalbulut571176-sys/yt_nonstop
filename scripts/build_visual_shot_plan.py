import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


ALLOWED_IMPORTANCE = {"hero", "supporting", "continuity", "bridge", "reuse"}
ALLOWED_GENERATION_MODES = {"unique", "derived", "reused"}


def infer_scene_importance(index: int, total: int, duration: float) -> str:
    if index == 1 or index == total:
        return "hero"
    if duration >= 4.0:
        return "supporting"
    if duration <= 1.6:
        return "bridge"
    return "continuity"


def build_default_plan(project: dict, package: dict) -> dict:
    items = package.get("items", [])
    total = len(items)
    shots = []
    scene_groups = []
    scene_to_shot = {}

    for index, item in enumerate(items, start=1):
        scene_id = item["scene_id"]
        shot_id = f"shot_{index:04d}"
        importance = infer_scene_importance(index, total, float(item.get("duration", 0) or 0))
        visual_anchor = (
            str(item.get("what_is_in_frame") or item.get("primary_subject") or item.get("visual_goal") or item.get("voice_text") or "")
            .strip()
        )
        shot_record = {
            "shot_id": shot_id,
            "importance": importance,
            "generation_mode": "unique",
            "primary_scene_id": scene_id,
            "scene_ids": [scene_id],
            "visual_anchor": visual_anchor,
            "off_topic_risk": "unknown",
            "prompt_strategy": "one concrete documentary shot per scene until grouping is explicitly authored",
            "primary_subject": str(item.get("primary_subject", "")).strip(),
        }
        shots.append(shot_record)
        scene_groups.append(
            {
                "group_id": f"group_{index:04d}",
                "importance": importance,
                "visual_strategy": "single-scene unique shot placeholder",
                "shot_id": shot_id,
                "scenes": [scene_id],
                "variation_notes": {},
            }
        )
        scene_to_shot[scene_id] = {
            "shot_id": shot_id,
            "generation_mode": "unique",
            "source_shot_id": shot_id,
            "variation_note": "",
        }

    return {
        "project_id": project["project_id"],
        "quality_mode": project["prompts"].get("quality_mode", "standard"),
        "total_scenes": total,
        "target_unique_shots": total,
        "actual_unique_shots": total,
        "planning_source": "prompt_package.json",
        "scene_groups": scene_groups,
        "shots": shots,
        "scene_to_shot": scene_to_shot,
    }


def normalize_plan(raw_plan: dict, scene_ids: set[str], quality_mode: str) -> dict:
    scene_groups = raw_plan.get("scene_groups", [])
    shots = raw_plan.get("shots", [])
    scene_to_shot = raw_plan.get("scene_to_shot", {})

    shots_by_id = {}
    normalized_shots = []
    for shot in shots:
        shot_id = str(shot.get("shot_id", "")).strip()
        if not shot_id or shot_id in shots_by_id:
            continue
        importance = str(shot.get("importance", "supporting")).strip() or "supporting"
        if importance not in ALLOWED_IMPORTANCE:
            importance = "supporting"
        generation_mode = str(shot.get("generation_mode", "unique")).strip() or "unique"
        if generation_mode not in ALLOWED_GENERATION_MODES:
            generation_mode = "unique"
        scene_ids_for_shot = [scene_id for scene_id in shot.get("scene_ids", []) if scene_id in scene_ids]
        primary_scene_id = str(shot.get("primary_scene_id", "")).strip() or (scene_ids_for_shot[0] if scene_ids_for_shot else "")
        normalized = {
            "shot_id": shot_id,
            "importance": importance,
            "generation_mode": generation_mode,
            "primary_scene_id": primary_scene_id,
            "scene_ids": scene_ids_for_shot,
            "visual_anchor": str(shot.get("visual_anchor", "")).strip(),
            "off_topic_risk": str(shot.get("off_topic_risk", "unknown")).strip() or "unknown",
            "prompt_strategy": str(shot.get("prompt_strategy", "")).strip(),
            "primary_subject": str(shot.get("primary_subject", "")).strip(),
        }
        shots_by_id[shot_id] = normalized
        normalized_shots.append(normalized)

    normalized_scene_to_shot = {}
    for scene_id, mapping in scene_to_shot.items():
        if scene_id not in scene_ids:
            continue
        shot_id = str(mapping.get("shot_id", "")).strip()
        if shot_id not in shots_by_id:
            continue
        generation_mode = str(mapping.get("generation_mode", shots_by_id[shot_id]["generation_mode"])).strip() or shots_by_id[shot_id]["generation_mode"]
        if generation_mode not in ALLOWED_GENERATION_MODES:
            generation_mode = shots_by_id[shot_id]["generation_mode"]
        source_shot_id = str(mapping.get("source_shot_id", shot_id)).strip() or shot_id
        normalized_scene_to_shot[scene_id] = {
            "shot_id": shot_id,
            "generation_mode": generation_mode,
            "source_shot_id": source_shot_id,
            "variation_note": str(mapping.get("variation_note", "")).strip(),
        }

    for group in scene_groups:
        shot_id = str(group.get("shot_id", "")).strip()
        if shot_id not in shots_by_id:
            continue
        for scene_id in group.get("scenes", []):
            if scene_id not in scene_ids or scene_id in normalized_scene_to_shot:
                continue
            normalized_scene_to_shot[scene_id] = {
                "shot_id": shot_id,
                "generation_mode": shots_by_id[shot_id]["generation_mode"],
                "source_shot_id": shot_id,
                "variation_note": str(group.get("variation_notes", {}).get(scene_id, "")).strip(),
            }

    return {
        "project_id": raw_plan.get("project_id"),
        "quality_mode": quality_mode,
        "total_scenes": len(scene_ids),
        "target_unique_shots": int(raw_plan.get("target_unique_shots", len(normalized_shots)) or len(normalized_shots)),
        "actual_unique_shots": len(normalized_shots),
        "planning_source": str(raw_plan.get("planning_source", "visual_bible.json")).strip() or "visual_bible.json",
        "scene_groups": scene_groups,
        "shots": normalized_shots,
        "scene_to_shot": normalized_scene_to_shot,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--input-json", help="Optional authored visual_shot_plan.json to normalize into the project path.")
    parser.add_argument("--quality-mode", choices=["premium", "standard", "fast"])
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    output_path = Path(project["prompts"]["visual_shot_plan_path"])
    quality_mode = args.quality_mode or project["prompts"].get("quality_mode", "standard")

    package = load_json(prompt_package_path)
    scene_ids = {item["scene_id"] for item in package.get("items", [])}
    if not scene_ids:
        raise RuntimeError("prompt_package has no scenes; cannot build visual_shot_plan")

    if args.input_json:
        raw_plan = load_json(Path(args.input_json).resolve())
        plan = normalize_plan(raw_plan, scene_ids, quality_mode)
    else:
        plan = build_default_plan(project, package)
        plan["quality_mode"] = quality_mode

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, plan)

    project["prompts"]["quality_mode"] = quality_mode
    project["prompts"]["visual_shot_plan_path"] = str(output_path)
    project["prompts"]["visual_shot_plan_status"] = "planned"
    save_project(project_json, project)

    print(output_path)


if __name__ == "__main__":
    main()
