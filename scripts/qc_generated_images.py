import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_json(project_json)
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

    qc_dir = project_root / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    qc_results_path = qc_dir / "qc_results.json"
    selection_manifest_path = qc_dir / "selection_manifest.json"
    qc_report_path = project_root / "logs" / "qc_report.md"

    qc_results = []
    selections = []
    for manifest_item in run_manifest:
        scene = scenes.get(manifest_item["scene_id"])
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
        qc_results.append(
            {
                "image_id": f"{manifest_item['scene_id']}_{manifest_item['variant_label']}",
                "scene_id": manifest_item["scene_id"],
                "variant_index": manifest_item["variant_index"],
                "file_path": record["output_file"],
                **scores,
                "notes": f"Metadata-based QC for {scene['beat_priority']} beat.",
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
        selections.append(
            {
                "scene_id": scene_id,
                "beat_priority": scene["beat_priority"],
                "key_beat": scene["key_beat"],
                "selected_image_id": winner["image_id"],
                "selected_image_path": winner["file_path"],
                "variant_count_evaluated": len(ordered),
                "winner_score": winner["final_score"],
                "selection_status": winner["decision"],
            }
        )
        report_lines.extend(
            [
                f"## {scene_id}",
                f"Selected: {winner['image_id']}",
                f"Winner score: {winner['final_score']}",
                f"Selection status: {winner['decision']}",
                f"Variants evaluated: {len(ordered)}",
                "",
            ]
        )

    qc_results_path.write_text(json.dumps(qc_results, ensure_ascii=False, indent=2), encoding="utf-8")
    selection_manifest_path.write_text(json.dumps(selections, ensure_ascii=False, indent=2), encoding="utf-8")
    qc_report_path.write_text("\n".join(report_lines), encoding="utf-8")

    project["qc"]["status"] = "completed"
    project["qc"]["qc_report_path"] = str(qc_report_path)
    project["qc"]["results_json_path"] = str(qc_results_path)
    project["images"]["selection_manifest_path"] = str(selection_manifest_path)
    project["images"]["generated_count"] = len(success_records)
    project["images"]["failed_count"] = max(0, len(run_manifest) - len(success_records))
    project["current_stage"] = "motion_plan"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(qc_results_path)
    print(selection_manifest_path)
    print(qc_report_path)


if __name__ == "__main__":
    main()
