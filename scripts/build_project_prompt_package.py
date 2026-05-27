import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from prompt_continuity import (
    build_continuity_bundle,
    build_scene_prompt,
    read_source_text,
    run_prompt_package_qa,
    stable_hash,
)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_review_blocks(items: list[dict]) -> str:
    blocks = []
    for item in items:
        blocks.append(
            "\n".join(
                [
                    f"Scene {item['shot_index']} ({item['scene_id']})",
                    f"Timing: {item['start']:.3f}-{item['end']:.3f}s",
                    f"Duration: {item['duration']:.3f}s",
                    f"Voice text: {item['voice_text']}",
                    f"Reference IDs: {', '.join(item.get('reference_ids', [])) if item.get('reference_ids') else 'none'}",
                    f"Shot role: {item['shot_role']}",
                    f"Beat priority: {item['beat_priority']}",
                    f"Key beat: {item['key_beat']}",
                    f"Primary subject: {item['primary_subject']}",
                    f"Viewer emotion: {item['semantic_descriptor']['viewer_emotion']}",
                    f"Scale: {item['scale']}",
                    f"Lighting family: {item['lighting_family']}",
                    f"Density: {item['density']}",
                    "Visual goal:",
                    item["visual_goal"],
                    "Prompt:",
                    item["prompt"],
                ]
            ).rstrip()
        )
    return "\n\n".join(blocks).rstrip() + "\n"


def build_prompt_integrity_report(package: dict, qa_result: dict) -> str:
    lines = [
        "# Prompt Integrity Report",
        "",
        f"Status: {qa_result['status']}",
        f"Theme hint: {package['theme_hint']}",
        f"Scene count: {package['scene_count']}",
        f"Source signature: {package['source_signature']}",
        "",
        "## QA Issues",
    ]
    if qa_result["issues"]:
        lines.extend(f"- {issue}" for issue in qa_result["issues"])
    else:
        lines.append("- none")
    lines.extend(["", "## QA Warnings"])
    if qa_result["warnings"]:
        lines.extend(f"- {warning}" for warning in qa_result["warnings"])
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def build_prompt_diversity_report(items: list[dict]) -> str:
    lines = [
        "# Prompt Diversity Report",
        "",
        "Shot role sequence:",
    ]
    lines.extend(f"- {item['scene_id']}: {item['shot_role']}" for item in items)
    lines.extend(["", "Environment sequence:"])
    lines.extend(f"- {item['scene_id']}: {item['environment']}" for item in items)
    lines.extend(["", "Adjacent diversity:"])
    lines.extend(
        f"- {item['scene_id']}: {', '.join(item.get('diversity_axes_from_previous', [])) or 'opening frame'}"
        for item in items
    )
    return "\n".join(lines).rstrip() + "\n"


def build_pre_generation_gate_report(package: dict, qa_result: dict) -> str:
    gate_status = "PASS" if qa_result["status"] == "passed" else "FAIL"
    lines = [
        "# Pre-Generation Gate Report",
        "",
        f"Gate status: {gate_status}",
        f"Prompt package path: {package['package_path']}",
        f"Source signature: {package['source_signature']}",
        "",
        "Generation is allowed only when gate status is PASS.",
    ]
    if qa_result["issues"]:
        lines.extend(["", "Blocking issues:"])
        lines.extend(f"- {issue}" for issue in qa_result["issues"])
    return "\n".join(lines).rstrip() + "\n"


def build_final_scene_plan(package: dict) -> dict:
    scenes = []
    for item in package["items"]:
        scenes.append(
            {
                "scene_id": item["scene_id"],
                "shot_index": item["shot_index"],
                "start": item["start"],
                "end": item["end"],
                "duration": item["duration"],
                "voice_text": item["voice_text"],
                "semantic_action": item["semantic_descriptor"]["semantic_action"],
                "event_type": item["semantic_descriptor"]["event_type"],
                "part_semantic_role": item["semantic_descriptor"]["part_semantic_role"],
                "event_clarity_required": item["semantic_descriptor"]["event_clarity_required"],
                "visual_function": item["semantic_descriptor"]["visual_function"],
                "visual_strategy": item["semantic_descriptor"]["visual_strategy"],
                "viewer_emotion": item["semantic_descriptor"]["viewer_emotion"],
                "role_confidence": item["semantic_descriptor"]["role_confidence"],
                "fallback_reason": item["semantic_descriptor"]["fallback_reason"],
                "shot_role": item["shot_role"],
                "beat_priority": item["beat_priority"],
                "key_beat": item["key_beat"],
                "scale": item["scale"],
                "primary_subject": item["primary_subject"],
                "environment": item["environment"],
                "composition": item["composition"],
                "angle": item["angle"],
                "lighting": item["lighting"],
                "lighting_family": item["lighting_family"],
                "atmosphere": item["atmosphere"],
                "density": item["density"],
                "pattern_break_score": item["pattern_break_score"],
                "diversity_axes_from_previous": item["diversity_axes_from_previous"],
                "prompt": item["prompt"],
            }
        )
    return {
        "project_id": package["project_id"],
        "schema_version": package["schema_version"],
        "source_signature": package["source_signature"],
        "prompt_package_path": package["package_path"],
        "scene_count": len(scenes),
        "scenes": scenes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = json.loads(project_json.read_text(encoding="utf-8"))
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    project_root = Path(project["meta"]["project_root"])
    prompts_dir = project_root / "prompts"
    config_dir = project_root / "config"
    logs_dir = project_root / "logs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    prompt_review_path = Path(project["prompts"]["prompt_review_path"])
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    continuity_path = config_dir / "continuity_entities.json"
    scene_context_path = prompts_dir / "scene_context_pack.json"
    integrity_report_path = logs_dir / "prompt_integrity_report.md"
    diversity_report_path = logs_dir / "prompt_diversity_report.md"
    gate_report_path = logs_dir / "pre_generation_gate_report.md"

    source_text = read_source_text(project)
    continuity_bundle = build_continuity_bundle(project, scene_plan.get("scenes", []), source_text)

    items = []
    for scene in scene_plan.get("scenes", []):
        authored = build_scene_prompt(scene, continuity_bundle)
        descriptor = authored["semantic_descriptor"]
        item = {
            "scene_id": scene["scene_id"],
            "shot_index": scene["shot_index"],
            "source_segment_id": scene["source_segment_id"],
            "part_index": scene["part_index"],
            "parts_total": scene["parts_total"],
            "start": scene["start"],
            "end": scene["end"],
            "duration": scene["duration"],
            "voice_text": scene["voice_text"],
            "visual_goal": authored["visual_goal"],
            "visual_intent": authored["visual_intent"],
            "reference_ids": scene.get("reference_ids", []),
            "reference_mode": scene.get("reference_mode", "none"),
            "prompt": authored["prompt"],
            "prompt_language": project["prompts"]["prompt_language"],
            "style_summary": "Premium cinematic documentary still, photorealistic, realistic lens perspective, atmospheric depth, natural imperfections, 16:9 composition, no text.",
            "continuity_world": continuity_bundle["continuity_world"],
            "continuity_rules": continuity_bundle["continuity_rules"],
            "recurring_motifs": continuity_bundle["recurring_motifs"],
            "theme_hint": continuity_bundle["theme_hint"],
            "shot_role": authored["shot_role"],
            "beat_priority": scene["beat_priority"],
            "key_beat": scene["key_beat"],
            "variant_count": 4 if scene["beat_priority"] == "hero" else 2 if scene["key_beat"] else 1,
            "primary_subject": authored["primary_subject"],
            "environment": authored["environment"],
            "composition": authored["composition"],
            "angle": authored["angle"],
            "lighting": authored["lighting"],
            "lighting_family": authored["lighting_family"],
            "atmosphere": authored["atmosphere"],
            "scale": authored["scale"],
            "density": authored["density"],
            "pattern_break_score": scene["pattern_break_score"],
            "diversity_axes_from_previous": scene.get("diversity_axes_from_previous", []),
            "active_entity_ids": authored["active_entity_ids"],
            "continuity_cast": authored["continuity_cast"],
            "continuity_focus": authored["continuity_focus"],
            "prompt_sections": authored["prompt_sections"],
            "semantic_descriptor": descriptor,
            "status": "pending_prompt",
            "notes": [],
        }
        items.append(item)

        scene["visual_goal"] = authored["visual_goal"]
        scene["prompt"] = authored["prompt"]
        scene["shot_role"] = authored["shot_role"]
        scene["primary_subject"] = authored["primary_subject"]
        scene["environment"] = authored["environment"]
        scene["composition"] = authored["composition"]
        scene["angle"] = authored["angle"]
        scene["lighting"] = authored["lighting"]
        scene["atmosphere"] = authored["atmosphere"]
        scene["active_entity_ids"] = authored["active_entity_ids"]
        scene["continuity_cast"] = authored["continuity_cast"]
        scene["continuity_focus"] = authored["continuity_focus"]
        scene["visual_intent"] = authored["visual_intent"]
        scene.update(descriptor)

    source_signature = stable_hash(
        [
                {
                    "scene_id": item["scene_id"],
                    "voice_text": item["voice_text"],
                    "shot_role": item["shot_role"],
                    "beat_priority": item["beat_priority"],
                    "primary_subject": item["primary_subject"],
                    "environment": item["environment"],
                    "prompt": item["prompt"],
                "semantic_descriptor": item["semantic_descriptor"],
            }
            for item in items
        ]
    )

    package = {
        "project_id": project["project_id"],
        "profile_id": project["profile_id"],
        "schema_version": project["schema_version"],
        "prompt_language": project["prompts"]["prompt_language"],
        "style_preset": project["prompts"]["style_preset"],
        "continuity_world": continuity_bundle["continuity_world"],
        "continuity_rules": continuity_bundle["continuity_rules"],
        "recurring_motifs": continuity_bundle["recurring_motifs"],
        "theme_hint": continuity_bundle["theme_hint"],
        "scene_count": len(items),
        "package_path": str(prompt_package_path),
        "built_at": iso_now(),
        "source_signature": source_signature,
        "items": items,
    }
    qa_result = run_prompt_package_qa(items, continuity_bundle["theme_hint"])
    package["qa_status"] = qa_result

    prompt_package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_review_path.write_text(build_review_blocks(items), encoding="utf-8")
    continuity_path.write_text(json.dumps(continuity_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    scene_context_path.write_text(
        json.dumps(
            [
                {
                    "scene_id": item["scene_id"],
                    "shot_index": item["shot_index"],
                    "voice_text": item["voice_text"],
                    "prompt_language": item["prompt_language"],
                    "theme_hint": item["theme_hint"],
                    "shot_role": item["shot_role"],
                    "beat_priority": item["beat_priority"],
                    "key_beat": item["key_beat"],
                    "variant_count": item["variant_count"],
                    "primary_subject": item["primary_subject"],
                    "environment": item["environment"],
                    "semantic_descriptor": item["semantic_descriptor"],
                    "active_entity_ids": item["active_entity_ids"],
                    "continuity_focus": item["continuity_focus"],
                    "scale": item["scale"],
                    "lighting_family": item["lighting_family"],
                    "density": item["density"],
                }
                for item in items
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    final_scene_plan_path.write_text(
        json.dumps(build_final_scene_plan(package), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    integrity_report_path.write_text(build_prompt_integrity_report(package, qa_result), encoding="utf-8")
    diversity_report_path.write_text(build_prompt_diversity_report(items), encoding="utf-8")
    gate_report_path.write_text(build_pre_generation_gate_report(package, qa_result), encoding="utf-8")
    scene_plan_path.write_text(json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    project["prompts"]["status"] = "package_built" if qa_result["status"] == "passed" else "qa_failed"
    project["prompts"]["scene_context_pack_path"] = str(scene_context_path)
    project["prompts"]["source_signature"] = source_signature
    project["prompts"]["qa_status"] = qa_result["status"]
    project.setdefault("logs", {})["prompt_integrity_report_path"] = str(integrity_report_path)
    project["logs"]["prompt_diversity_report_path"] = str(diversity_report_path)
    project["logs"]["pre_generation_gate_report_path"] = str(gate_report_path)
    project["current_stage"] = "publishing_drafts" if qa_result["status"] == "passed" else "prompt_qa_failed"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(prompt_package_path)
    print(prompt_review_path)
    print(final_scene_plan_path)
    print(continuity_path)
    print(scene_context_path)


if __name__ == "__main__":
    main()
