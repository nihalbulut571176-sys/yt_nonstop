import argparse
import html
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project


def load_rows(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    rows = payload.get(key, []) if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    selected_rows = load_rows(Path(project["images"]["selected_images_manifest_path"]), "selected_images")
    continuity = load_json(Path(project["qc"]["continuity_qc_report_path"])) if Path(project["qc"]["continuity_qc_report_path"]).exists() else {}
    regeneration = load_json(Path(project["qc"]["regeneration_plan_path"])) if Path(project["qc"]["regeneration_plan_path"]).exists() else {"tasks": []}
    output_path = Path(project["qc"]["review_package_html_path"])
    decisions_path = Path(project["qc"]["review_decisions_path"])

    row_html = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('scene_id', '')))}</td>"
        f"<td>{html.escape(str(row.get('selection_status', '')))}</td>"
        f"<td>{html.escape(str(row.get('coverage_status', '')))}</td>"
        f"<td>{html.escape(str(row.get('visualized_claim', '')))}</td>"
        "</tr>"
        for row in selected_rows
    )
    warnings = continuity.get("warnings", []) if isinstance(continuity, dict) else []
    tasks = regeneration.get("tasks", []) if isinstance(regeneration, dict) else []
    body = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Review Package</title></head>
<body>
  <h1>Review Package</h1>
  <p>Selected images: {len(selected_rows)}</p>
  <p>Continuity warnings: {len(warnings)}</p>
  <p>Regeneration tasks: {len(tasks)}</p>
  <table border="1" cellspacing="0" cellpadding="4">
    <thead><tr><th>Scene</th><th>Status</th><th>Coverage</th><th>Claim</th></tr></thead>
    <tbody>{row_html}</tbody>
  </table>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")
    if not decisions_path.exists():
        save_json(
            decisions_path,
            {
                "decisions": [
                    {"scene_id": row.get("scene_id"), "status": "approve", "notes": "Golden sample default approval"}
                    for row in selected_rows
                    if row.get("scene_id")
                ]
            },
        )
    project.setdefault("qc", {})["review_package_html_path"] = str(output_path)
    project["current_stage"] = "human_review"
    save_project(project_json, project)
    print(output_path)


if __name__ == "__main__":
    main()
