from pathlib import Path


SOURCE = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_no_timestamps.md")
TARGET = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_numbered.md")


def main() -> None:
    blocks = [block.strip() for block in SOURCE.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    lines = []
    for index, block in enumerate(blocks, start=1):
        lines.append(f"{index}.")
        lines.append(block)
        lines.append("")
    TARGET.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
