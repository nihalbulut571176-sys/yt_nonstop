import argparse
from pathlib import Path

from build_project_scene_plan import merge_into_sentence_blocks, parse_srt
from pipeline_contracts import SceneMap
from project_pipeline_utils import load_project, save_json, save_project


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    srt_path = Path(project["scene_plan"]["source_srt_path"] or project["transcription"]["srt_path"])
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT not found: {srt_path}")

    segments = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
    sentence_blocks = merge_into_sentence_blocks(segments)
    scene_map = SceneMap(
        project_id=project["project_id"],
        source_srt_path=str(srt_path),
        sentence_blocks=sentence_blocks,
        segment_count=len(sentence_blocks),
    )

    scene_map_path = Path(project["planning"]["scene_map_path"])
    sentence_blocks_json_path = Path(project["planning"]["sentence_blocks_json_path"])
    sentence_blocks_txt_path = Path(project["planning"]["sentence_blocks_txt_path"])
    scene_map_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(scene_map_path, scene_map.__dict__)
    save_json(sentence_blocks_json_path, sentence_blocks)
    sentence_blocks_txt_path.write_text(
        "\n".join(
            f"{item['segment_id']}. [{item['start_tc']} - {item['end_tc']}] {item['text']}"
            for item in sentence_blocks
        )
        + "\n",
        encoding="utf-8",
    )

    project["planning"]["status"] = "ingested"
    project["current_stage"] = "build_scene_map"
    save_project(project_json, project)
    print(scene_map_path)


if __name__ == "__main__":
    main()
