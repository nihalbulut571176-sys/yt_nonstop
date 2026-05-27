import argparse
import importlib.util
import json
import re
from difflib import SequenceMatcher
from pathlib import Path


def normalize(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я\s]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_xlsx_rows(workspace_root: Path, xlsx_path: Path) -> list[dict]:
    helper_path = workspace_root / "scripts" / "generate_master_test_batch_parallel.py"
    spec = importlib.util.spec_from_file_location("generate_master_test_batch_parallel", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load workbook reader from {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_xlsx_sheet_objects(xlsx_path, "Generation_Master")


def load_segments(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def score_match(excerpt: str, window_text: str) -> float:
    a = normalize(excerpt)
    b = normalize(window_text)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    a_tokens = a.split()
    b_tokens = b.split()
    overlap = len(set(a_tokens) & set(b_tokens)) / max(1, len(set(a_tokens)))
    prefix_bonus = 0.08 if b.startswith(a[: min(len(a), 24)]) or a.startswith(b[: min(len(b), 24)]) else 0.0
    return ratio * 0.7 + overlap * 0.3 + prefix_bonus


def build_window_text(segments: list[dict], start_idx: int, window_len: int) -> str:
    return " ".join(segment["text"] for segment in segments[start_idx : start_idx + window_len])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--xlsx-path", required=True)
    parser.add_argument("--segments-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    xlsx_path = Path(args.xlsx_path).resolve()
    segments_path = Path(args.segments_path).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_xlsx_rows(workspace_root, xlsx_path)
    segments = load_segments(segments_path)

    aligned = []
    prev_start_idx = 0
    prev_end_idx = 0

    for row_index, row in enumerate(rows, start=1):
        excerpt = row.get("voiceover_excerpt", "")
        best = None
        search_start = max(0, prev_start_idx - 1)
        search_end = min(len(segments) - 1, prev_end_idx + 8)

        for seg_start in range(search_start, search_end + 1):
            for window_len in range(1, 5):
                seg_end = seg_start + window_len - 1
                if seg_end >= len(segments):
                    continue
                window_text = build_window_text(segments, seg_start, window_len)
                score = score_match(excerpt, window_text)
                if best is None or score > best["score"]:
                    best = {
                        "seg_start": seg_start,
                        "seg_end": seg_end,
                        "score": score,
                        "window_text": window_text,
                    }

        if best is None:
            raise RuntimeError(f"Could not align row {row_index} {row.get('id')}")

        prev_start_idx = best["seg_start"]
        prev_end_idx = best["seg_end"]
        start_segment = segments[best["seg_start"]]
        end_segment = segments[best["seg_end"]]
        aligned.append(
            {
                "row_index": row_index,
                "id": row.get("id"),
                "section": row.get("section", ""),
                "voiceover_excerpt": excerpt,
                "matched_segment_start_id": start_segment["id"],
                "matched_segment_end_id": end_segment["id"],
                "matched_text": best["window_text"],
                "start": start_segment["start"],
                "end": end_segment["end"],
                "duration": round(float(end_segment["end"]) - float(start_segment["start"]), 6),
                "score": round(best["score"], 6),
            }
        )

    output = {
        "row_count": len(rows),
        "segment_count": len(segments),
        "aligned_rows": aligned,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "row_count": len(rows),
                "avg_score": round(sum(item["score"] for item in aligned) / len(aligned), 6),
                "min_score": round(min(item["score"] for item in aligned), 6),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
