import json
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
TIMELINE_PATH = ROOT / "edit" / "timeline.json"
VIDEO_DIR = ROOT / "veononstop_run" / "videos"
TARGETS_PATH = ROOT / "edit" / "animation_targets.json"
TARGET_TIMELINE_PATH = ROOT / "edit" / "animation_target_timeline.json"
MIXED_MANIFEST_PATH = ROOT / "edit" / "mixed_asset_manifest.json"


def main() -> None:
    timeline = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    existing_videos = {
        int(path.stem): str(path)
        for path in VIDEO_DIR.glob("*.mp4")
        if path.stem.isdigit()
    }

    post_minute = [shot for shot in timeline if float(shot["start"]) >= 60.0]
    post_order = {int(shot["shot_index"]): idx + 1 for idx, shot in enumerate(post_minute)}

    targets = []
    target_timeline = []
    mixed_manifest = []

    for shot in timeline:
        shot_index = int(shot["shot_index"])
        start = float(shot["start"])
        first_minute = start < 60.0
        after_first_minute = not first_minute
        post_index = post_order.get(shot_index)
        target_video = first_minute or (after_first_minute and post_index is not None and (post_index - 1) % 3 == 0)

        video_path = existing_videos.get(shot_index)
        chosen_asset_type = "video" if target_video and video_path else "image"
        chosen_asset_path = video_path if target_video and video_path else str(Path(shot["image"]))

        record = {
            "shot_index": shot_index,
            "start": float(shot["start"]),
            "end": float(shot["end"]),
            "duration": float(shot["duration"]),
            "generated_index": int(shot["generated_index"]),
            "image": str(shot["image"]),
            "source_kind": shot.get("source_kind"),
            "prompt": shot.get("prompt"),
            "target_video": target_video,
            "existing_video": video_path,
            "chosen_asset_type": chosen_asset_type,
            "chosen_asset_path": chosen_asset_path,
        }
        targets.append(record)
        mixed_manifest.append(record)
        if target_video:
            target_timeline.append(shot)

    TARGETS_PATH.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")
    TARGET_TIMELINE_PATH.write_text(json.dumps(target_timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    MIXED_MANIFEST_PATH.write_text(json.dumps(mixed_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "total_shots": len(timeline),
        "target_video_shots": len(target_timeline),
        "existing_target_videos": sum(1 for item in targets if item["target_video"] and item["existing_video"]),
        "missing_target_videos": sum(1 for item in targets if item["target_video"] and not item["existing_video"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
