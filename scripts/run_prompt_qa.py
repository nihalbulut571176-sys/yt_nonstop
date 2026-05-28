import argparse
import json
from pathlib import Path

from llm_pipeline_contracts import iso_now
from project_pipeline_utils import load_project, save_project
from prompt_safety import lint_event_clarity, lint_prompt_observability


DISALLOWED_PROMPT_MARKERS = ["dialogue", "say the", "speaks to camera"]
NEGATIVE_ONLY_MARKERS = ["lip-sync", "subtitles"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--use-final-scene-plan", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    preferred_scene_source = Path(project["prompts"]["final_scene_plan_path"]) if args.use_final_scene_plan else Path(project["scene_plan"]["scene_plan_path"])
    scene_source = preferred_scene_source if preferred_scene_source.exists() else Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_source.read_text(encoding="utf-8"))
    draft_records = None
    if not args.use_final_scene_plan:
        drafts_path = Path(project["prompts"]["llm_prompt_drafts_path"])
        if drafts_path.exists():
            draft_records = {record["scene_id"]: record for record in json.loads(drafts_path.read_text(encoding="utf-8"))}
    report_path = Path(project["logs"]["prompt_qa_report_path"])
    json_path = Path(project["logs"]["prompt_qa_json_path"])

    errors: list[str] = []
    warnings: list[str] = []
    rewrite_targets: list[dict[str, str]] = []
    for scene in scene_plan.get("scenes", []):
        scene_id = scene["scene_id"]
        prompt_source = draft_records.get(scene_id, {}) if draft_records is not None else scene
        prompt = str(prompt_source.get("final_prompt") or prompt_source.get("prompt", "")).strip()
        if not prompt:
            errors.append(f"{scene_id} is missing final prompt")
            rewrite_targets.append({"scene_id": scene_id, "reason": "missing_final_prompt"})
            continue
        lowered = prompt.lower()
        for marker in DISALLOWED_PROMPT_MARKERS:
            if marker in lowered:
                errors.append(f"{scene_id} contains disallowed prompt marker: {marker}")
                rewrite_targets.append({"scene_id": scene_id, "reason": f"disallowed_marker:{marker}"})
        for marker in NEGATIVE_ONLY_MARKERS:
            if marker in lowered and f"no {marker}" not in lowered and f"without {marker}" not in lowered:
                errors.append(f"{scene_id} contains positive disallowed prompt marker: {marker}")
                rewrite_targets.append({"scene_id": scene_id, "reason": f"positive_disallowed_marker:{marker}"})
        if len(prompt) < 80:
            warnings.append(f"{scene_id} prompt may be too thin")
        observability_warnings = lint_prompt_observability(
            prompt=prompt,
            primary_subject=str(prompt_source.get("primary_subject", scene.get("primary_subject", ""))),
            what_is_in_frame=str(prompt_source.get("what_is_in_frame", scene.get("what_is_in_frame", ""))),
            event_clarity_required=bool(prompt_source.get("event_clarity_required", scene.get("event_clarity_required", False))),
        )
        for warning in observability_warnings:
            message = f"{scene_id}: {warning}"
            if bool(prompt_source.get("event_clarity_required", scene.get("event_clarity_required", False))) and "Event-critical scene" in warning:
                errors.append(message)
                rewrite_targets.append({"scene_id": scene_id, "reason": "event_clarity_failure"})
            else:
                warnings.append(message)
        if bool(prompt_source.get("event_clarity_required", scene.get("event_clarity_required", False))):
            event_warnings = lint_event_clarity(
                prompt=prompt,
                primary_subject=str(prompt_source.get("primary_subject", scene.get("primary_subject", ""))),
                what_is_in_frame=str(prompt_source.get("what_is_in_frame", scene.get("what_is_in_frame", ""))),
                event_type=str(prompt_source.get("event_type", scene.get("event_type", ""))),
            )
            for warning in event_warnings:
                errors.append(f"{scene_id}: {warning}")
                rewrite_targets.append({"scene_id": scene_id, "reason": "event_semantic_failure"})
        scene.setdefault("qa_status", {})
        scene["qa_status"]["prompt_qa"] = "approved"

    status = "approved" if not errors else "rejected"
    scene_plan["prompt_qa_status"] = status
    scene_source.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    json_path.write_text(json.dumps({"status": status, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(
        "# Prompt QA Report\n\n"
        f"Status: {status}\n\n"
        "## Errors\n"
        + ("\n".join(errors) if errors else "- none")
        + "\n\n## Warnings\n"
        + ("\n".join(warnings) if warnings else "- none")
        + "\n",
        encoding="utf-8",
    )
    rewrite_queue = {
        "created_at": iso_now(),
        "source": "run_prompt_qa",
        "failure_type": "semantic_prompt_rewrite",
        "items": [],
    }
    seen_targets: set[str] = set()
    for target in rewrite_targets:
        scene_id = target["scene_id"]
        if scene_id in seen_targets:
            continue
        seen_targets.add(scene_id)
        rewrite_queue["items"].append(target)
    Path(project["prompts"]["rewrite_queue_path"]).write_text(
        json.dumps(rewrite_queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if errors:
        project["prompts"]["status"] = "failed"
    else:
        project["current_stage"] = "apply_llm_prompt_drafts" if not args.use_final_scene_plan else "generate_images"
    save_project(project_json, project)
    print(report_path)


if __name__ == "__main__":
    main()
