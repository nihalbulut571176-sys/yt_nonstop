from pathlib import Path


SOURCE = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_refs_no_numbering.md")
TARGET = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_inline_refs.md")


def main() -> None:
    blocks = [block.strip().splitlines() for block in SOURCE.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    output_blocks = []
    for lines in blocks:
        if len(lines) < 2:
            continue
        ref_line = lines[0].strip()
        prompt_line = " ".join(line.strip() for line in lines[1:] if line.strip())
        output_blocks.append(f"{ref_line}, {prompt_line}")
    TARGET.write_text("\n\n".join(output_blocks).rstrip() + "\n", encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
