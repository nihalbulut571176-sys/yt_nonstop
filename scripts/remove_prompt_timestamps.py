from pathlib import Path


SOURCE = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_timed_visual_prompts.md")
TARGET = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_no_timestamps.md")


def is_timestamp_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.endswith("]") and ". [" in stripped


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    cleaned = [line for line in lines if not is_timestamp_line(line)]
    TARGET.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
