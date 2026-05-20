import argparse
import json
import shutil
from pathlib import Path


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def normalize_name(path: Path) -> str:
    stem = path.stem.lower()
    return stem


def collect_images(folder: Path):
    return sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS],
        key=lambda p: normalize_name(p),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--generated-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    generated_root = Path(args.generated_root)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    grouped = {}
    for item in manifest:
        grouped.setdefault(item["group"], []).append(item)

    problems = []
    for group, items in grouped.items():
        group_dir = generated_root / group
        if not group_dir.exists():
            problems.append(f"Missing folder for group: {group}")
            continue

        images = collect_images(group_dir)
        if len(images) != len(items):
            problems.append(
                f"Group {group}: expected {len(items)} images, found {len(images)} in {group_dir}"
            )
            continue

        for item, image_path in zip(items, images):
            target_name = f"{item['global_index']:03d}{image_path.suffix.lower()}"
            target_path = output_dir / target_name
            shutil.copy2(image_path, target_path)

    if problems:
        raise SystemExit("\n".join(problems))

    print(output_dir)


if __name__ == "__main__":
    main()
