import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


NON_GENERATIVE_DECISIONS = {"hold_previous", "continuation_motion"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    allocation_path = Path(project["planning"]["visual_allocation_plan_path"])
    payload = load_json(allocation_path)
    slots = payload.get("visual_slots", []) if isinstance(payload, dict) else []

    generative_slots = [slot for slot in slots if str(slot.get("generation_decision", "")).strip() not in NON_GENERATIVE_DECISIONS]
    planned_variants = sum(max(0, int(slot.get("variant_count", 0) or 0)) for slot in generative_slots)
    hold_slots = sum(1 for slot in slots if str(slot.get("generation_decision", "")).strip() in NON_GENERATIVE_DECISIONS)
    estimated_cost_usd = round(planned_variants * 0.01, 2)

    report = {
        "project_id": project.get("project_id"),
        "visual_slots_count": len(slots),
        "generative_slots_count": len(generative_slots),
        "hold_or_continuation_slots_count": hold_slots,
        "planned_variants_count": planned_variants,
        "estimated_cost_usd": estimated_cost_usd,
        "notes": "Deterministic no-API estimate based on authored visual allocation slots and planned variants.",
    }
    json_path = Path(project["reports"]["generation_estimate_json_path"])
    md_path = Path(project["reports"]["generation_estimate_md_path"])
    save_json(json_path, report)
    md_path.write_text(
        "\n".join(
            [
                "# Generation Estimate",
                "",
                f"- Visual slots: {len(slots)}",
                f"- Generative slots: {len(generative_slots)}",
                f"- Hold/continuation slots: {hold_slots}",
                f"- Planned variants: {planned_variants}",
                f"- Estimated cost (USD): {estimated_cost_usd:.2f}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    project.setdefault("generation", {})["estimate_status"] = "completed"
    project["generation"]["estimated_cost_usd"] = estimated_cost_usd
    project["reports"]["generation_estimate_json_path"] = str(json_path)
    project["reports"]["generation_estimate_md_path"] = str(md_path)
    project["current_stage"] = "build_visual_shot_plan"
    save_project(project_json, project)
    print(json_path)


if __name__ == "__main__":
    main()
