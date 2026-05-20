import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start-shot", type=int, required=True)
    parser.add_argument("--step", type=int, required=True)
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    timeline = json.loads(source.read_text(encoding="utf-8"))

    filtered = [
        shot
        for shot in timeline
        if int(shot["shot_index"]) >= args.start_shot
        and (int(shot["shot_index"]) - args.start_shot) % args.step == 0
    ]

    output.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "source_count": len(timeline),
                "filtered_count": len(filtered),
                "start_shot": args.start_shot,
                "step": args.step,
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
