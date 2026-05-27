import argparse
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_project


ALLOWED_NON_STRICT = {"locked", "locked_with_warnings"}
ALLOWED_STRICT = {"locked"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--require-filled-prompts", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    locked_rows = load_json(Path(project["prompts"]["generation_locked_json_path"]))
    export_path = Path(project["prompts"]["fastgen_export_path"])
    generator_ready_path = Path(project["prompts"]["generator_ready_path"])
    export_report_path = Path(project["logs"]["export_report_path"])

    allowed = ALLOWED_STRICT if project["workflow"].get("strict_generation_lock") else ALLOWED_NON_STRICT
    eligible = [row for row in locked_rows if row["generation_lock_status"] in allowed]
    blocked = [row["frame_id"] for row in locked_rows if row["generation_lock_status"] not in allowed]
    if args.require_filled_prompts and blocked:
        raise RuntimeError(f"Generation lock blocked frames: {', '.join(blocked[:20])}")

    text = "\n\n".join(row["generator_block"] for row in eligible).strip() + "\n"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(text, encoding="utf-8")
    if generator_ready_path != export_path:
        generator_ready_path.write_text(text, encoding="utf-8")

    export_report_path.write_text(
        "\n".join(
            [
                "# Export Report",
                "",
                f"Locked frames available: {len(eligible)}",
                f"Blocked frames: {len(blocked)}",
                f"Strict mode: {project['workflow'].get('strict_generation_lock')}",
                f"Output: {export_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    project["prompts"]["status"] = "generator_ready"
    project["current_stage"] = "report"
    save_project(project_json, project)
    print(export_path)


if __name__ == "__main__":
    main()
