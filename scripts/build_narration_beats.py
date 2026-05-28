import argparse
from pathlib import Path

from pipeline_contracts import dedupe_strings, normalize_text
from project_pipeline_utils import load_json, load_project, save_json, save_project


def derive_spoken_claim(scene: dict) -> str:
    return normalize_text(
        scene.get("scene_meaning")
        or scene.get("visual_goal")
        or scene.get("narrative_purpose")
        or scene.get("voice_text", "")
    )


def derive_must_visualize(scene: dict) -> list[str]:
    candidates = [
        scene.get("primary_subject", ""),
        scene.get("what_is_in_frame", ""),
        scene.get("visual_idea", ""),
        scene.get("main_subject", ""),
        scene.get("environment", ""),
        scene.get("voice_text", ""),
    ]
    values = [normalize_text(value) for value in candidates if normalize_text(value)]
    if not values:
        values = [normalize_text(scene.get("voice_text", ""))]
    return dedupe_strings(values[:3])


def derive_beat_role(scene: dict) -> str:
    for candidate in (
        scene.get("visual_function"),
        scene.get("narrative_purpose"),
        scene.get("shot_role"),
        scene.get("event_type"),
    ):
        value = normalize_text(str(candidate or "")).lower()
        if value:
            return value.replace(" ", "_")
    return "explanation"


def derive_visual_priority(scene: dict) -> str:
    importance = normalize_text(str(scene.get("scene_importance") or "")).lower()
    if scene.get("event_clarity_required") or importance in {"hero", "key"}:
        return "high"
    if importance in {"supporting", "continuity"}:
        return "medium"
    return "low"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_plan = load_json(Path(project["scene_plan"]["scene_plan_path"]))
    output_path = Path(project["planning"]["narration_beats_path"])

    beats = []
    for index, scene in enumerate(scene_plan.get("scenes", []), start=1):
        beat_id = str(scene.get("beat_id") or f"beat_{index:04d}")
        entity_mentions = dedupe_strings(
            [str(item) for item in scene.get("subject_ids", [])]
            + [str(item) for item in scene.get("mentioned_subject_ids", [])]
            + [str(item) for item in scene.get("active_entity_ids", [])]
        )
        location_mentions = dedupe_strings(
            [str(scene.get("environment", "")), str(scene.get("location_id", ""))]
        )
        beat = {
            "beat_id": beat_id,
            "scene_id": scene["scene_id"],
            "start": float(scene["start"]),
            "end": float(scene["end"]),
            "duration": float(scene["duration"]),
            "voice_text": str(scene.get("voice_text", "")),
            "spoken_claim": derive_spoken_claim(scene),
            "must_visualize": derive_must_visualize(scene),
            "entity_mentions": entity_mentions,
            "location_mentions": location_mentions,
            "beat_role": derive_beat_role(scene),
            "visual_priority": derive_visual_priority(scene),
        }
        beats.append(beat)
        scene["beat_id"] = beat_id

    save_json(output_path, {"project_id": project["project_id"], "beats": beats})
    save_json(Path(project["scene_plan"]["scene_plan_path"]), scene_plan)
    project["planning"]["status"] = "narration_beats_built"
    project["current_stage"] = "build_frame_briefs"
    save_project(project_json, project)
    print(output_path)


if __name__ == "__main__":
    main()
