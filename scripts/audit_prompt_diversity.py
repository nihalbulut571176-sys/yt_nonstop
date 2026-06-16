import argparse
import json
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from project_pipeline_utils import load_project
from yt_nonstop.utils.text_repair import repair_mojibake_text


def clean_text(value: str) -> str:
    return " ".join(repair_mojibake_text(str(value or "")).replace("\n", " ").split()).strip()


def similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--start-shot", type=int, default=1)
    parser.add_argument("--end-shot", type=int, default=40)
    args = parser.parse_args()

    project = load_project(Path(args.project_json).resolve())
    final_scene_plan_path = Path(project["prompts"]["final_scene_plan_path"])
    payload = json.loads(final_scene_plan_path.read_text(encoding="utf-8"))
    scenes = [
        scene
        for scene in payload.get("scenes", [])
        if args.start_shot <= int(scene.get("shot_index") or 0) <= args.end_shot
    ]

    report = {
        "project_id": project["project_id"],
        "range": [args.start_shot, args.end_shot],
        "scene_count": len(scenes),
        "by_shot_role": Counter(scene.get("shot_role") or "" for scene in scenes),
        "by_main_subject": Counter(clean_text(scene.get("main_subject")) for scene in scenes),
        "by_composition": Counter(clean_text(scene.get("composition")) for scene in scenes),
        "prompt_similarity_pairs": [],
    }

    for left_index, left in enumerate(scenes):
        left_prompt = clean_text(left.get("final_prompt") or left.get("prompt") or "")
        for right in scenes[left_index + 1 :]:
            right_prompt = clean_text(right.get("final_prompt") or right.get("prompt") or "")
            score = similarity(left_prompt, right_prompt)
            if score >= 0.94:
                report["prompt_similarity_pairs"].append(
                    {
                        "scene_a": left["scene_id"],
                        "scene_b": right["scene_id"],
                        "score": round(score, 4),
                        "shot_role_a": left.get("shot_role"),
                        "shot_role_b": right.get("shot_role"),
                        "main_subject_a": clean_text(left.get("main_subject")),
                        "main_subject_b": clean_text(right.get("main_subject")),
                    }
                )

    report_path = final_scene_plan_path.parent / f"prompt_audit_{args.start_shot:04d}_{args.end_shot:04d}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
