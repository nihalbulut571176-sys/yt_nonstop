import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from image_semantic_qc import default_image_semantic_qc_adapter
from llm_pipeline_contracts import inspect_image_file
from pipeline_contracts import dedupe_strings, normalize_text, normalize_text_lower
from project_pipeline_utils import load_json, load_project, save_json, save_project


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_generation_manifest(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        rows = payload.get("generated_images", [])
        if isinstance(rows, list):
            return rows
        raise RuntimeError("Unsupported run_manifest format: `generated_images` must be a list")
    if isinstance(payload, list):
        return payload
    raise RuntimeError("Unsupported run_manifest format")


def build_scores(scene: dict, record: dict) -> dict:
    hook = 9 if scene.get("beat_priority") == "hero" else 8 if scene.get("key_beat") else 7
    realism = 8
    relevance = 9 if scene.get("shot_role") and scene.get("prompt") else 6
    non_slideshow = min(10, max(6, int(round(float(scene.get("pattern_break_score", 6.0) or 6.0)))))
    motion_potential = 9 if scene.get("visual_function") in {"hook", "payoff", "pattern_break"} else 8 if scene.get("visual_strategy") == "mechanism_view" else 7
    continuity = 9 if scene.get("active_entity_ids") else 7
    freshness = 9 if len(scene.get("diversity_axes_from_previous", [])) >= 3 else 7
    artifact_risk = 2 if record.get("status") == "success" else 7
    final_score = round((hook + realism + relevance + non_slideshow + motion_potential + continuity + freshness + (10 - artifact_risk)) / 8, 2)
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
    }


def prompt_semantic_coverage(scene: dict) -> tuple[str, list[str]]:
    flags: list[str] = []
    must_show = dedupe_strings([str(item) for item in scene.get("must_show", []) if str(item).strip()])
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
    return ("pass" if not flags else "fail"), flags


def required_reference_missing(scene: dict) -> bool:
    entity_locks = scene.get("entity_locks", [])
    required_entities = [item for item in entity_locks if item.get("reference_policy") == "required" or item.get("identity_lock") == "required"]
    if not required_entities:
        return False
    return not bool(scene.get("reference_ids"))


def selection_allowed(selection_status: str) -> bool:
    return selection_status in {"use", "manual_review"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    project_root = Path(project["meta"]["project_root"])
    prompt_package = load_json(Path(project["prompts"]["prompt_package_path"]))
    manifest_payload = load_json(Path(project["images"]["run_manifest_path"]))
    generated_rows = normalize_generation_manifest(manifest_payload)

    scenes = {scene["scene_id"]: scene for scene in prompt_package["items"]}
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    final_scene_plan = load_json(final_scene_plan_path) if final_scene_plan_path.exists() else {"scenes": []}
    final_scene_by_id = {scene["scene_id"]: scene for scene in final_scene_plan.get("scenes", []) if scene.get("scene_id")}
    narration_beats_path = Path(project["planning"].get("narration_beats_path", ""))
    narration_beats = load_json(narration_beats_path).get("beats", []) if narration_beats_path.exists() else []
    beats_by_scene = {beat.get("scene_id"): beat for beat in narration_beats if beat.get("scene_id")}

    qc_results_path = Path(project["images"]["image_qc_report_path"])
    selection_manifest_path = Path(project["images"]["selected_images_manifest_path"])
    qc_report_path = project_root / "logs" / "qc_report.md"
    adapter = default_image_semantic_qc_adapter()

    grouped_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in generated_rows:
        scene_id = row.get("scene_id")
        if scene_id:
            grouped_records[scene_id].append(row)

    qc_results = []
    selections = []
    report_lines = ["# QC Report", "", f"Generated at: {iso_now()}", ""]
    ordered_scene_ids = [scene["scene_id"] for scene in prompt_package.get("items", []) if scene.get("scene_id")]

    for position, scene_id in enumerate(ordered_scene_ids):
        results = grouped_records.get(scene_id, [])
        scene = final_scene_by_id.get(scene_id) or scenes.get(scene_id)
        if not scene:
            continue
        beat = beats_by_scene.get(scene_id, {})
        if not results:
            continue

        current_context = {
            "beat_id": scene.get("beat_id") or beat.get("beat_id"),
            "voice_text": scene.get("voice_text", beat.get("voice_text", "")),
            "visualized_claim": scene.get("visualized_claim", beat.get("spoken_claim", "")),
            "must_show": scene.get("must_show", beat.get("must_visualize", [])),
            "film_block_id": scene.get("film_block_id", ""),
        }
        neighbor_contexts = []
        if position > 0:
            prev_scene = final_scene_by_id.get(ordered_scene_ids[position - 1]) or scenes.get(ordered_scene_ids[position - 1], {})
            neighbor_contexts.append({"film_block_id": prev_scene.get("film_block_id", "")})
        if position + 1 < len(ordered_scene_ids):
            next_scene = final_scene_by_id.get(ordered_scene_ids[position + 1]) or scenes.get(ordered_scene_ids[position + 1], {})
            neighbor_contexts.append({"film_block_id": next_scene.get("film_block_id", "")})

        scene_results = []
        prompt_coverage_status, prompt_semantic_flags = prompt_semantic_coverage(scene)
        if required_reference_missing(scene):
            prompt_semantic_flags.append("missing_required_reference_lock")

        for record in results:
            image_path = Path(record.get("normalized_image_path") or record.get("image_path") or "")
            semantic = adapter.evaluate(
                image_path=image_path,
                beat_context=current_context,
                reference_ids=list(scene.get("reference_ids", [])),
                neighbor_contexts=neighbor_contexts,
            )
            inspection = inspect_image_file(image_path) if image_path else {"exists": False, "readable": False}
            semantic_flags = sorted(set(prompt_semantic_flags + list(semantic.get("semantic_flags", []))))
            coverage_status = "pass" if prompt_coverage_status == "pass" and semantic.get("coverage_status") == "pass" and not semantic_flags else "fail"
            technical_qc_passed = bool(record.get("status") == "success" and inspection.get("exists") and inspection.get("readable"))
            decision = str(semantic.get("decision", "manual_review"))
            if not technical_qc_passed:
                decision = "reject"
            elif coverage_status != "pass" and decision == "use":
                decision = "manual_review"
            if scene.get("key_beat") and int(record.get("variant_count", 1) or 1) < 2 and decision == "use":
                decision = "manual_review"

            row = {
                "image_id": f"{scene_id}_{record.get('variant_label') or f'V{int(record.get('variant_index', 1) or 1):02d}'}",
                "scene_id": scene_id,
                "beat_id": current_context["beat_id"],
                "variant_index": int(record.get("variant_index", 1) or 1),
                "variant_label": str(record.get("variant_label") or f"V{int(record.get('variant_index', 1) or 1):02d}"),
                "file_path": str(image_path) if image_path else "",
                "normalized_image_path": str(record.get("normalized_image_path") or image_path) if image_path else "",
                "voice_text": current_context["voice_text"],
                "visualized_claim": current_context["visualized_claim"],
                "must_show": current_context["must_show"],
                "prompt_semantic_status": prompt_coverage_status,
                "prompt_semantic_flags": prompt_semantic_flags,
                "vlm_caption": semantic.get("vlm_caption", ""),
                "must_show_coverage": semantic.get("must_show_coverage", []),
                "identity_check": semantic.get("identity_check", {}),
                "style_continuity_check": semantic.get("style_continuity_check", {}),
                "technical_qc_passed": technical_qc_passed,
                "coverage_status": coverage_status,
                "semantic_flags": semantic_flags,
                "decision": decision,
                **build_scores(scene, record),
                "notes": "Adapter-backed image semantic QC with prompt-grounding fallback.",
            }
            scene_results.append(row)
            qc_results.append(row)

        ordered = sorted(
            scene_results,
            key=lambda item: (
                1 if item["decision"] == "use" else 0,
                1 if item["decision"] == "manual_review" else 0,
                item["technical_qc_passed"],
                item["coverage_status"] == "pass",
                item["final_score"],
            ),
            reverse=True,
        )
        winner = ordered[0]
        selections.append(
            {
                "scene_id": scene_id,
                "beat_id": winner.get("beat_id"),
                "beat_priority": scene.get("beat_priority", scene.get("scene_importance", "standard")),
                "key_beat": scene.get("key_beat", False),
                "selected_image_id": winner["image_id"],
                "selected_image_path": winner["file_path"],
                "normalized_image_path": winner.get("normalized_image_path", winner["file_path"]),
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

    save_json(qc_results_path, {"project_id": project["project_id"], "created_at": iso_now(), "images": qc_results})
    save_json(selection_manifest_path, {"project_id": project["project_id"], "created_at": iso_now(), "selected_images": selections})
    qc_report_path.parent.mkdir(parents=True, exist_ok=True)
    qc_report_path.write_text("\n".join(report_lines), encoding="utf-8")

    project["qc"]["status"] = "completed"
    project["qc"]["qc_report_path"] = str(qc_report_path)
    project["qc"]["results_json_path"] = str(qc_results_path)
    project["images"]["selected_images_manifest_path"] = str(selection_manifest_path)
    project["images"]["image_qc_report_path"] = str(qc_results_path)
    project["images"]["generated_count"] = sum(1 for item in generated_rows if item.get("status") == "success")
    project["images"]["failed_count"] = sum(1 for item in generated_rows if item.get("status") != "success")
    project["current_stage"] = "normalize_images"
    save_project(project_json, project)

    print(qc_results_path)
    print(selection_manifest_path)
    print(qc_report_path)


if __name__ == "__main__":
    main()
