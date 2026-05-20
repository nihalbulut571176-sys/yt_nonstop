import re
from pathlib import Path


SRT_PATH = Path(r"C:\Users\MIKE\Documents\Codex\YT\transcript_fw\message@elevenLabsVoicerBot.srt")
OUT_PATH = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_blocks_from_srt.txt")


def parse_srt(text: str):
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        start, end = lines[1].split(" --> ")
        content = " ".join(line.strip() for line in lines[2:])
        segments.append({"start": start, "end": end, "text": content})
    return segments


def merge_into_sentence_blocks(segments):
    sentence_blocks = []
    current = []
    for seg in segments:
        current.append(seg)
        if re.search(r"[.!?…]$", seg["text"]):
            sentence_blocks.append(
                {
                    "start": current[0]["start"],
                    "end": current[-1]["end"],
                    "text": re.sub(r"\s+", " ", " ".join(item["text"] for item in current)).strip(),
                }
            )
            current = []
    if current:
        sentence_blocks.append(
            {
                "start": current[0]["start"],
                "end": current[-1]["end"],
                "text": re.sub(r"\s+", " ", " ".join(item["text"] for item in current)).strip(),
            }
        )
    return sentence_blocks


def main():
    srt_text = SRT_PATH.read_text(encoding="utf-8")
    segments = parse_srt(srt_text)
    sentence_blocks = merge_into_sentence_blocks(segments)

    lines = []
    for index, item in enumerate(sentence_blocks, start=1):
        lines.append(f"{index}. [{item['start']} - {item['end']}] {item['text']}")
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(OUT_PATH)


if __name__ == "__main__":
    main()
