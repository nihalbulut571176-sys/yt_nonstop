from pathlib import Path


SOURCE = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_numbered_with_refs.md")
TARGET = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_only.md")


def is_number_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.endswith(".") and stripped[:-1].isdigit()


def is_ref_line(line: str) -> bool:
    stripped = line.strip()
    return stripped == "No Ref" or stripped.startswith("Ref:")


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    cleaned = [line for line in lines if not is_number_line(line) and not is_ref_line(line)]
    TARGET.write_text("\n".join(cleaned).rstrip() + "\n", encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
