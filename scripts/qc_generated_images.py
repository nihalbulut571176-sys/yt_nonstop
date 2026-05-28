import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pipeline_contracts import dedupe_strings, normalize_text, normalize_text_lower
from project_pipeline_utils import load_project, save_json, save_project


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def build_scores(scene: dict, record: dict) -> dict:
    hook = 9 if scene.get("beat_priority") == "hero" else 8 if scene.get("key_beat") else 7
    realism = 8
    relevance = 9 if scene.get("shot_role") and scene.get("prompt") else 6
    non_slideshow = min(10, max(6, int(round(float(scene.get("pattern_break_score", 6.0))))))
    motion_potential = 9 if scene.get("visual_function") in {"hook", "payoff", "pattern_break"} else 8 if scene.get("visual_strategy") == "mechanism_view" else 7
    continuity = 9 if scene.get("active_entity_ids") else 7
    freshness = 9 if len(scene.get("diversity_axes_from_previous", [])) >= 3 else 7
    artifact_risk = 2 if record.get("status") == "success" else 7
    final_score = round((hook + realism + relevance + non_slideshow + motion_potential + continuity + freshness + (10 - artifact_risk)) / 8, 2)
    decision = "use" if final_score >= 8 else "manual_review" if final_score >= 7 else "reject"
    return {
        "visual_hook": hook,
        "documentary_realism": realism,
        "story_relevance": relevance,
        "non_slideshow_value": non_slideshow,
        "motion_potential": motion_potential,
        "continuity": continuity,
        "artifact_risk": artifact_risk,
        "freshness": freshness,
        "final_score": final_score,
        "decision": decision,
    }


def required_reference_missing(scene: dict) -> bool:
    entity_locks = scene.get("entity_locks", [])
    required_entities = [item for item in entity_locks if item.get("reference_policy") == "required" or item.get("identity_lock") == "required"]
    if not required_entities:
        return False
    return not bool(scene.get("reference_ids"))


def semantic_coverage(scene: dict, record: dict) -> tuple[str, list[str]]:
    flags: list[str] = []
    must_show = dedupe_strings([str(item) for item in scene.get("must_show", [])])
    visualized_claim = normalize_text(scene.get("visualized_claim", ""))
    prompt_blob = normalize_text_lower(
        " ".join(
            [
                str(scene.get("image_prompt_final", "")),
                str(scene.get("final_prompt", "")),
                str(scene.get("prompt", "")),
                str(scene.get("why_this_frame_exists", "")),
            ]
        )
    )
    if not must_show:
        flags.append("missing_must_show")
    elif not any(normalize_text_lower(item) in prompt_blob for item in must_show if normalize_text_lower(item)):
        flags.append("must_show_not_grounded_in_prompt")
    if not visualized_claim:
        flags.append("missing_visualized_claim")
    elif normalize_text_lower(visualized_claim) not in prompt_blob:
        flags.append("visualized_claim_not_grounded_in_prompt")
    if required_reference_missing(scene):
        flags.append("missing_required_reference_lock")
    return ("pass" if not flags else "fail"), flags


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    project_root = Path(project["meta"]["project_root"])
    prompt_package = load_json(Path(project["prompts"]["prompt_package_path"]))
    run_manifest = load_json(Path(project["images"]["run_manifest_path"]))
    success_log_path = Path(project["images"]["run_manifest_path"]).parent / "success.jsonl"
    success_records = []
    if success_log_path.exists():
        for line in success_log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                success_records.append(json.loads(line))

    scenes = {scene["scene_id"]: scene for scene in prompt_package["items"]}
    success_by_scene = defaultdict(list)
    for record in success_records:
        success_by_scene[record["scene_id"]].append(record)

    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    final_scene_plan = load_json(final_scene_plan_path) if final_scene_plan_path.exists() else {"scenes": []}
    final_scene_by_id = {scene["scene_id"]: scene for scene in final_scene_plan.get("scenes", []) if scene.get("scene_id")}
    narration_beats_path = Path(project["planning"].get("narration_beats_path", ""))
    narration_beats = load_json(narration_beats_path).get("beats", []) if narration_beats_path.exists() else []
    beats_by_scene = {beat.get("scene_id"): beat for beat in narration_beats if beat.get("scene_id")}

    qc_dir = project_root / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    qc_results_path = Path(project["images"]["image_qc_report_path"])
    selection_manifest_path = Path(project["images"]["selected_images_manifest_path"])
    qc_report_path = project_root / "logs" / "qc_report.md"

    qc_results = []
    selections = []
    for manifest_item in run_manifest:
        scene = final_scene_by_id.get(manifest_item["scene_id"]) or scenes.get(manifest_item["scene_id"])
        if not scene:
            continue
        record = next(
            (
                item
                for item in success_by_scene.get(manifest_item["scene_id"], [])
                if int(item.get("variant_index", 0)) == int(manifest_item["variant_index"])
            ),
            None,
        )
        if record is None:
            continue
        scores = build_scores(scene, record)
        coverage_status, semantic_flags = semantic_coverage(scene, record)
        beat = beats_by_scene.get(manifest_item["scene_id"], {})
        qc_results.append(
            {
                "image_id": f"{manifest_item['scene_id']}_{manifest_item['variant_label']}",
                "scene_id": manifest_item["scene_id"],
                "beat_id": scene.get("beat_id") or beat.get("beat_id"),
                "variant_index": manifest_item["variant_index"],
                "file_path": record["output_file"],
                "voice_text": scene.get("voice_text", beat.get("voice_text", "")),
                "visualized_claim": scene.get("visualized_claim", beat.get("spoken_claim", "")),
                "must_show": scene.get("must_show", beat.get("must_visualize", [])),
                "coverage_status": coverage_status,
                "semantic_flags": semantic_flags,
                **scores,
                "notes": f"Metadata-based QC for {scene.get('beat_priority', scene.get('scene_importance', 'standard'))} beat.",
            }
        )

    grouped = defaultdict(list)
    for result in qc_results:
        grouped[result["scene_id"]].append(result)

    report_lines = ["# QC Report", "", f"Generated at: {iso_now()}", ""]
    for scene_id, results in grouped.items():
        ordered = sorted(results, key=lambda item: item["final_score"], reverse=True)
        winner = ordered[0]
        scene = scenes[scene_id]
        if scene.get("key_beat") and len(ordered) < 2:
            winner["decision"] = "manual_review"
        if winner["coverage_status"] != "pass":
            winner["decision"] = "reject"
        selections.append(
            {
                "scene_id": scene_id,
                "beat_id": winner.get("beat_id"),
                "beat_priority": scene.get("beat_priority", scene.get("scene_importance", "standard")),
                "key_beat": scene.get("key_beat", False),
                "selected_image_id": winner["image_id"],
                "selected_image_path": winner["file_path"],
                "variant_count_evaluated": len(ordered),
                "winner_score": winner["final_score"],
                "selection_status": winner["decision"],
                "voice_text": winner.get("voice_text", ""),
                "visualized_claim": winner.get("visualized_claim", ""),
                "must_show": winner.get("must_show", []),
                "coverage_status": winner.get("coverage_status", "fail"),
                "semantic_flags": winner.get("semantic_flags", []),
            }
        )
        report_lines.extend(
            [
                f"## {scene_id}",
                f"Selected: {winner['image_id']}",
                f"Winner score: {winner['final_score']}",
                f"Selection status: {winner['decision']}",
                f"Coverage status: {winner['coverage_status']}",
                f"Variants evaluated: {len(ordered)}",
                "",
            ]
        )

    save_json(
        qc_results_path,
        {
            "project_id": project["project_id"],
            "created_at": iso_now(),
            "images": qc_results,
        },
    )
    save_json(
        selection_manifest_path,
        {
            "project_id": project["project_id"],
            "created_at": iso_now(),
            "selected_images": selections,
        },
    )
    qc_report_path.write_text("\n".join(report_lines), encoding="utf-8")

    project["qc"]["status"] = "completed"
    project["qc"]["qc_report_path"] = str(qc_report_path)
    project["qc"]["results_json_path"] = str(qc_results_path)
    project["images"]["selected_images_manifest_path"] = str(selection_manifest_path)
    project["images"]["image_qc_report_path"] = str(qc_results_path)
    project["images"]["generated_count"] = len(success_records)
    project["images"]["failed_count"] = max(0, len(run_manifest) - len(success_records))
    project["current_stage"] = "normalize_images"
    save_project(project_json, project)

    print(qc_results_path)
    print(selection_manifest_path)
    print(qc_report_path)


if __name__ == "__main__":
    main()
