import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    project_root = Path(project["meta"]["project_root"])
    continuity_bible_path = project_root / "config" / "continuity_bible.md"
    continuity_entities_path = project_root / "config" / "continuity_entities.json"
    continuity_bible_path.parent.mkdir(parents=True, exist_ok=True)

    scene_plan = json.loads(Path(project["scene_plan"]["scene_plan_path"]).read_text(encoding="utf-8"))
    motifs = ["glass reflections", "surveillance systems", "documents and maps", "anonymous human consequence", "digital traces"]
    entities = {
        "recurring_motifs": motifs,
        "continuity_rules": [
            "Prefer anonymous figures over identifiable faces.",
            "Reuse the same visual world motifs without repeating the same composition three times in a row.",
            "Keep technology and documentary props grounded and non-fantastical.",
        ],
        "scene_count": len(scene_plan.get("scenes", [])),
    }
    continuity_bible_path.write_text(
        "# Continuity Bible\n\n"
        "Keep recurring motifs coherent without making the visual row repetitive.\n\n"
        + "\n".join(f"- {item}" for item in entities["continuity_rules"])
        + "\n",
        encoding="utf-8",
    )
    continuity_entities_path.write_text(json.dumps(entities, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    project["current_stage"] = "prompt_package"
    save_project(project_json, project)
    print(continuity_bible_path)


if __name__ == "__main__":
    main()
