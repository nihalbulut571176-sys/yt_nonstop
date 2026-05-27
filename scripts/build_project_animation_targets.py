import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def choose_target_video(shot: dict, policy_name: str, post_order: dict[int, int]) -> bool:
    shot_index = int(shot["shot_index"])
    start = float(shot["start"])
    if policy_name == "none":
        return False
    if policy_name == "all":
        return True
    if policy_name == "first_minute_then_every_third":
        if start < 60.0:
            return True
        post_index = post_order.get(shot_index)
        return post_index is not None and (post_index - 1) % 3 == 0
    raise ValueError(f"Unsupported animation policy: {policy_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--policy", default="first_minute_then_every_third")
    parser.add_argument("--videos-dir", default="")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_json(project_json)
    project_root = Path(project["meta"]["project_root"])
    timeline_path = Path(project["render"]["slideshow_timeline_path"])
    timeline = load_json(timeline_path)

    animation_dir = project_root / "animation"
    animation_dir.mkdir(parents=True, exist_ok=True)
    videos_dir = Path(args.videos_dir) if args.videos_dir else animation_dir / "veononstop_run" / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    post_minute = [shot for shot in timeline if float(shot["start"]) >= 60.0]
    post_order = {int(shot["shot_index"]): idx + 1 for idx, shot in enumerate(post_minute)}

    targets = []
    target_timeline = []
    mixed_manifest = []

    for shot in timeline:
        shot_index = int(shot["shot_index"])
        target_video = choose_target_video(shot, args.policy, post_order)
        video_path = videos_dir / f"{shot_index:03d}.mp4"
        has_video = video_path.exists() and video_path.stat().st_size > 0
        chosen_asset_type = "video" if target_video and has_video else "image"
        chosen_asset_path = str(video_path if target_video and has_video else Path(shot["image"]))

        record = {
            "scene_id": shot["scene_id"],
            "shot_index": shot_index,
            "start": float(shot["start"]),
            "end": float(shot["end"]),
            "duration": float(shot["duration"]),
            "image": str(shot["image"]),
            "prompt": shot.get("prompt", ""),
            "voice_text": shot.get("voice_text", ""),
            "source_kind": shot.get("source_kind"),
            "target_video": target_video,
            "existing_video": str(video_path) if has_video else None,
            "chosen_asset_type": chosen_asset_type,
            "chosen_asset_path": chosen_asset_path,
        }
        targets.append(record)
        mixed_manifest.append(record)
        if target_video:
            target_timeline.append(
                {
                    "scene_id": shot["scene_id"],
                    "shot_index": shot_index,
                    "start": float(shot["start"]),
                    "end": float(shot["end"]),
                    "duration": float(shot["duration"]),
                    "image": str(shot["image"]),
                    "prompt": shot.get("prompt", ""),
                    "voice_text": shot.get("voice_text", ""),
                    "source_kind": shot.get("source_kind"),
                }
            )

    targets_path = animation_dir / "animation_targets.json"
    target_timeline_path = animation_dir / "animation_target_timeline.json"
    mixed_manifest_path = animation_dir / "mixed_asset_manifest.json"
    report_path = project_root / "logs" / "animation_targets_report.md"

    targets_path.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")
    target_timeline_path.write_text(json.dumps(target_timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    mixed_manifest_path.write_text(json.dumps(mixed_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report_lines = [
        "# Animation Targets Report",
        "",
        f"Policy: {args.policy}",
        f"Timeline source: {timeline_path}",
        f"Videos dir: {videos_dir}",
        f"Total shots: {len(timeline)}",
        f"Target video shots: {len(target_timeline)}",
        f"Existing target videos: {sum(1 for item in targets if item['target_video'] and item['existing_video'])}",
        f"Missing target videos: {sum(1 for item in targets if item['target_video'] and not item['existing_video'])}",
        f"Targets path: {targets_path}",
        f"Target timeline path: {target_timeline_path}",
        f"Mixed manifest path: {mixed_manifest_path}",
    ]
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    project["animation"]["status"] = "planned"
    project["animation"]["policy_name"] = args.policy
    project["animation"]["provider"] = "veononstop"
    project["animation"]["campaign_manifest_path"] = str(targets_path)
    project["animation"]["timeline_subset_path"] = str(target_timeline_path)
    project["animation"]["videos_dir"] = str(videos_dir)
    project["render"]["render_strategy"] = "mixed_cut"
    project["render"]["mixed_manifest_path"] = str(mixed_manifest_path)
    project["logs"]["animation_targets_report_path"] = str(report_path)
    project["current_stage"] = "animation_run"
    project["updated_at"] = iso_now()
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(target_timeline_path)
    print(mixed_manifest_path)


if __name__ == "__main__":
    main()
