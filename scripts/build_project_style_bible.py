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
    style_guide_path = Path(project["prompts"]["style_guide_path"])
    visual_bible_path = Path(project["prompts"]["visual_bible_path"])
    style_guide_path.parent.mkdir(parents=True, exist_ok=True)

    style_guide = {
        "style_summary": "Premium cinematic documentary, photorealistic, realistic lensing, motivated light, no cheap AI-art look, no slideshow feeling.",
        "palette": ["black glass", "steel gray", "paper beige", "monitor blue", "muted gold"],
        "camera_language": ["wide establishing", "medium documentary", "close-up detail", "macro texture", "over-the-shoulder", "reflection shot"],
        "forbidden_visuals": [
            "dialogue scenes",
            "lip-sync",
            "subtitles in frame",
            "generic stock-photo look",
            "random logos",
            "fake readable UI",
        ],
    }
    style_guide_path.write_text(json.dumps(style_guide, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    visual_bible_path.write_text(
        "\n".join(
            [
                "# Style Bible",
                "",
                "Premium cinematic documentary.",
                "Photorealistic.",
                "16:9 framing.",
                "Realistic lens perspective.",
                "Motivated lighting.",
                "No slideshow feeling.",
                "No random text or fake UI.",
                "No plastic faces or distorted hands.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    project["prompts"]["global_style_summary"] = style_guide["style_summary"]
    project["current_stage"] = "visual_direction"
    save_project(project_json, project)
    print(style_guide_path)


if __name__ == "__main__":
    main()
