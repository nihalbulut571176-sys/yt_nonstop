import json
import re
from pathlib import Path


SOURCE = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\sentence_visual_prompts_generator_ready.md")
OUT_DIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\deliverables\prompt_batches")

GROUP_ORDER = [
    "CHAR_01_Journalist",
    "CHAR_02_CrimeBoss",
    "CHAR_03_TeenageRecruit",
    "CHAR_04_FounderEngineer",
    "CHAR_05_CryptophoneEntrepreneur",
    "CHAR_06_IntelligenceAnalyst",
    "NO_REF",
]


def detect_group(prompt: str) -> str:
    if prompt.startswith("No character reference."):
        return "NO_REF"

    match_single = re.match(r"Use reference image:\s+([A-Za-z0-9_]+)\.", prompt)
    if match_single:
        return match_single.group(1)

    match_multi = re.match(r"Use reference images:\s+([A-Za-z0-9_]+(?:,\s*[A-Za-z0-9_]+)*)\.", prompt)
    if match_multi:
        refs = [item.strip() for item in match_multi.group(1).split(",")]
        return "__".join(refs)

    raise ValueError(f"Could not detect reference group for prompt: {prompt[:120]}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prompts = [block.strip() for block in SOURCE.read_text(encoding="utf-8").split("\n\n") if block.strip()]

    manifest = []
    grouped = {}
    for i, prompt in enumerate(prompts, start=1):
        group = detect_group(prompt)
        item = {
            "global_index": i,
            "group": group,
            "prompt": prompt,
        }
        manifest.append(item)
        grouped.setdefault(group, []).append(item)

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    all_groups = GROUP_ORDER + sorted(
        [group for group in grouped if group not in GROUP_ORDER],
        key=str.lower,
    )

    summary_lines = []
    for group in all_groups:
        items = grouped.get(group, [])
        if not items:
            continue

        txt_lines = []
        csv_lines = ["batch_index,global_index,group,prompt"]
        for batch_index, item in enumerate(items, start=1):
            txt_lines.append(item["prompt"])
            csv_prompt = item["prompt"].replace('"', '""')
            csv_lines.append(f'{batch_index},{item["global_index"]},{item["group"]},"{csv_prompt}"')

        (OUT_DIR / f"{group}.txt").write_text("\n\n".join(txt_lines) + "\n", encoding="utf-8")
        (OUT_DIR / f"{group}.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
        summary_lines.append(f"{group}: {len(items)}")

    (OUT_DIR / "SUMMARY.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(OUT_DIR)
    print(manifest_path)


if __name__ == "__main__":
    main()
