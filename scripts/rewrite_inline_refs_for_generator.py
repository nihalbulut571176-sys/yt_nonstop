from pathlib import Path


SOURCE = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_inline_refs.md")
TARGET = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_generator_ready.md")

REF_NAME_MAP = {
    "Journalist": "CHAR_01_Journalist",
    "Crime Boss": "CHAR_02_CrimeBoss",
    "Teenage Recruit": "CHAR_03_TeenageRecruit",
    "Founder Engineer": "CHAR_04_FounderEngineer",
    "Cryptophone Entrepreneur": "CHAR_05_CryptophoneEntrepreneur",
    "Intelligence Analyst": "CHAR_06_IntelligenceAnalyst",
}


def normalize_prefix(line: str) -> str:
    if line.startswith("No Ref, "):
        return "No character reference. " + line[len("No Ref, "):]

    if line.startswith("Ref: "):
        refs_part, prompt_part = line.split(", ", 1)
        raw_refs = refs_part[len("Ref: "):]
        refs = [REF_NAME_MAP[item.strip()] for item in raw_refs.split(",")]
        if len(refs) == 1:
            return f"Use reference image: {refs[0]}. {prompt_part}"
        return f"Use reference images: {', '.join(refs)}. {prompt_part}"

    return line


def main() -> None:
    blocks = [block.strip() for block in SOURCE.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    rewritten = [normalize_prefix(block) for block in blocks]
    TARGET.write_text("\n\n".join(rewritten).rstrip() + "\n", encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
