import argparse
import json
import re
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--videos-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-scene", type=int, default=51)
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--manifest", action="append", default=[])
    args = parser.parse_args()

    images_dir = Path(args.images_dir)
    videos_dir = Path(args.videos_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    prompt_lookup: dict[str, str] = {}
    for manifest_path_str in args.manifest:
        manifest_path = Path(manifest_path_str)
        if not manifest_path.exists():
            continue
        for item in load_json(manifest_path):
            scene_id = item.get("scene_id")
            prompt = item.get("prompt", "")
            if scene_id and prompt and scene_id not in prompt_lookup:
                prompt_lookup[scene_id] = prompt

    timeline = []
    cursor = 0.0
    for image_path in sorted(images_dir.glob("scene_*.png")):
        match = re.match(r"scene_(\d{4})_V\d+\.png$", image_path.name)
        if not match:
            continue
        scene_num = int(match.group(1))
        if scene_num < args.min_scene:
            continue
        video_name = f"{scene_num:03d}.mp4"
        video_path = videos_dir / video_name
        if video_path.exists() and video_path.stat().st_size > 0:
            continue
        scene_id = f"scene_{scene_num:04d}"
        timeline.append(
            {
                "scene_id": scene_id,
                "shot_index": scene_num,
                "start": round(cursor, 3),
                "end": round(cursor + args.duration, 3),
                "duration": args.duration,
                "image": str(image_path),
                "prompt": prompt_lookup.get(scene_id, ""),
                "source_kind": "missing_animation_catchup",
            }
        )
        cursor += args.duration

    output.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"timeline_path": str(output), "count": len(timeline)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
