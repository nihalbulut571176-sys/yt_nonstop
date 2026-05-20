import argparse
import subprocess
from pathlib import Path


DEFAULT_SOURCE_DIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\fastgen_run\images")
DEFAULT_OUTPUT_DIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\edit\normalized_images")
DEFAULT_WIDTH = 1672
DEFAULT_HEIGHT = 942


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    args = parser.parse_args()

    source_dir = Path(args.source)
    output_dir = Path(args.output)
    target_width = args.width
    target_height = args.height

    output_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(source_dir.glob("*.png"))
    if not images:
        raise RuntimeError(f"No source images found in {source_dir}")

    vf = (
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )

    for image in images:
        output = output_dir / image.name
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(image),
            "-vf",
            vf,
            str(output),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    print(output_dir)


if __name__ == "__main__":
    main()
