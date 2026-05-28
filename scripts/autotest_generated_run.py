import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from fastgen_openai_v4_generate import parse_prompt_blocks
from project_pipeline_utils import load_json, load_project, save_json, save_project
from v2_pipeline_lib import _infer_subject_ids_for_frame

try:
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover
    Image = None
    ImageFilter = None


HUMAN_SUBJECT_LABELS = {
    "lead_operator": "lead operator",
    "support_operator": "support operator",
    "security_guard": "security guard",
    "boutique_attendant": "boutique attendant",
}

SEVERE_META_PHRASES = (
    "forensic documentary clue",
    "unexpected visual turn",
    "fresh investigative purpose",
    "distinct explain image",
    "distinct evidence image",
    "distinct hook image",
    "distinct payoff image",
    "pattern_break image",
)

CONCEPTUAL_OPENERS = (
    "unexpected visual turn",
    "forensic documentary clue",
    "distance between",
    "absence of",
    "identity entering",
    "nickname born",
    "dark reality behind",
    "compressed heist timing",
    "international police pressure",
    "balkan network",
    "forensic breakdown",
    "target selection logic",
    "architecture, human reaction, and bureaucracy used as tools",
    "arrests failing",
    "closing investigative image",
)

ABSTRACT_TERMS = {
    "absence",
    "architecture",
    "bureaucracy",
    "camouflage",
    "clue",
    "context",
    "contrast",
    "distance",
    "echo",
    "evidence",
    "framing",
    "identity",
    "institutional",
    "investigative",
    "lag",
    "language",
    "logic",
    "mechanism",
    "media",
    "myth",
    "network",
    "pattern_break",
    "persistence",
    "pressure",
    "purpose",
    "reality",
    "response",
    "resolution",
    "reversal",
    "selection",
    "system",
    "target",
    "timing",
    "tone",
    "transnational",
    "turn",
}

CONCRETE_TERMS = {
    "attendant",
    "barrier",
    "boutique",
    "bystanders",
    "camera",
    "case",
    "city",
    "cream",
    "customers",
    "diamond",
    "display",
    "door",
    "entrants",
    "farm",
    "glass",
    "guard",
    "guarded",
    "hands",
    "headquarters",
    "jar",
    "jewel",
    "lighting",
    "necklace",
    "object",
    "operator",
    "operators",
    "passerby",
    "people",
    "shelf",
    "showroom",
    "stones",
    "street",
    "threshold",
    "uniforms",
    "worker",
}


def discover_run_dir(project: dict[str, Any], explicit_run_dir: str | None) -> Path:
    if explicit_run_dir:
        return Path(explicit_run_dir).resolve()
    images_root = Path(project["meta"]["project_root"]) / "images"
    candidates = [path for path in images_root.iterdir() if path.is_dir() and path.name.startswith("fastgen_run")]
    if not candidates:
        raise FileNotFoundError(f"No fastgen run directories found in {images_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_export_refs(project: dict[str, Any]) -> dict[str, list[str]]:
    export_path = Path(project["prompts"]["fastgen_export_path"])
    blocks = parse_prompt_blocks(export_path)
    final_scene_plan = load_json(Path(project["prompts"]["final_scene_plan_path"]))
    scenes = final_scene_plan.get("scenes", [])
    refs_by_scene: dict[str, list[str]] = {}
    for index, scene in enumerate(scenes):
        if index < len(blocks):
            refs_by_scene[scene["scene_id"]] = list(blocks[index].get("refs", []))
        else:
            refs_by_scene[scene["scene_id"]] = []
    return refs_by_scene


def average_hash(image_path: Path) -> str:
    if Image is None:
        return ""
    image = Image.open(image_path).convert("L").resize((8, 8))
    pixels = list(image.getdata())
    mean = sum(pixels) / len(pixels)
    return "".join("1" if pixel >= mean else "0" for pixel in pixels)


def hamming_distance(left: str, right: str) -> int:
    if not left or not right or len(left) != len(right):
        return 64
    return sum(1 for a, b in zip(left, right) if a != b)


def image_metrics(image_path: Path) -> dict[str, Any]:
    if Image is None:
        return {"image_exists": image_path.exists()}
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        gray = image.convert("L")
        width, height = rgb.size
        histogram = gray.histogram()
        total = sum(histogram) or 1
        entropy = 0.0
        for count in histogram:
            if count <= 0:
                continue
            probability = count / total
            entropy -= probability * math.log2(probability)
        pixels = list(gray.getdata())
        mean_luma = sum(pixels) / max(1, len(pixels))
        edge_variance = 0.0
        if ImageFilter is not None:
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_pixels = list(edges.getdata())
            edge_mean = sum(edge_pixels) / max(1, len(edge_pixels))
            edge_variance = sum((pixel - edge_mean) ** 2 for pixel in edge_pixels) / max(1, len(edge_pixels))
        return {
            "image_exists": True,
            "width": width,
            "height": height,
            "aspect_ratio": round(width / max(1, height), 4),
            "entropy": round(entropy, 4),
            "mean_luma": round(mean_luma, 2),
            "edge_variance": round(edge_variance, 2),
            "hash": average_hash(image_path),
        }


def classify_reference_need(scene: dict[str, Any], subject_registry: dict[str, dict[str, Any]], export_ref_ids: list[str]) -> tuple[list[str], bool, str]:
    frame_like = {
        "main_subject": scene.get("director_prompt", {}).get("visual_intent") or scene.get("image_prompt_final", ""),
        "mini_world": scene.get("mini_world", ""),
        "scene_meaning": scene.get("director_prompt", {}).get("scene_meaning", ""),
        "why_this_frame_exists": scene.get("why_this_frame_exists", ""),
        "voice_text": scene.get("voice_text", ""),
    }
    expected_subject_ids = _infer_subject_ids_for_frame(frame_like, set(subject_registry))
    needs_reference = bool(expected_subject_ids)
    if export_ref_ids and needs_reference:
        reason = "Human subject expected and reference prefix is present in export."
    elif export_ref_ids and not needs_reference:
        reason = "Reference prefix is present although subject inference did not require one; manual review recommended."
    elif not export_ref_ids and needs_reference:
        subject_names = ", ".join(HUMAN_SUBJECT_LABELS.get(subject_id, subject_id) for subject_id in expected_subject_ids)
        reason = f"Human subject expected ({subject_names}) but export prompt has no reference prefix."
    else:
        reason = "No concrete recurring person inferred for this frame."
    return expected_subject_ids, needs_reference, reason


def extract_core_visual_phrase(prompt: str) -> str:
    prompt = prompt.strip()
    match = re.search(r"16:9\.\s*(.+?)(?:,\s*inside\s+|$)", prompt, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return prompt


def normalize_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-zA-Z_]+", text.lower()) if len(word) > 2}


def semantic_prompt_audit(scene: dict[str, Any]) -> tuple[list[str], list[str], str]:
    prompt = str(scene.get("image_prompt_final", "") or "")
    core_phrase = extract_core_visual_phrase(prompt).lower()
    prompt_lower = prompt.lower()
    flags: list[str] = []
    notes: list[str] = []

    if any(phrase in prompt_lower for phrase in SEVERE_META_PHRASES):
        flags.append("severe_pipeline_meta_language")
        notes.append("Prompt contains pipeline/service wording instead of purely visual direction.")

    if "visual function" in prompt_lower or "frame purpose:" in prompt_lower:
        flags.append("embedded_pipeline_labels")
        notes.append("Prompt still exposes internal control labels that should stay out of generator-ready text.")

    if "revised after qc" in prompt_lower or "introduce a stronger pattern break" in prompt_lower:
        flags.append("qc_revision_leak")
        notes.append("QC revision notes leaked into the generator prompt.")

    if any(core_phrase.startswith(opener) for opener in CONCEPTUAL_OPENERS):
        flags.append("conceptual_core_not_filmable")
        notes.append("Core visual phrase reads like an abstract thesis instead of a camera-capturable shot.")

    words = normalize_words(core_phrase)
    abstract_hits = sorted(words.intersection(ABSTRACT_TERMS))
    concrete_hits = sorted(words.intersection(CONCRETE_TERMS))
    if abstract_hits and not concrete_hits:
        flags.append("abstract_core_without_physical_anchor")
        notes.append("Core phrase is dominated by abstract concepts and lacks a physical anchor in frame.")

    if len(concrete_hits) <= 1 and ("between" in words or "behind" in words or "logic" in words or "identity" in words):
        flags.append("weak_visual_staging")
        notes.append("Prompt does not clearly stage who or what the camera should show in a specific physical setup.")

    if "silent documentary image" in prompt_lower or "no speaking characters" in prompt_lower:
        flags.append("redundant_negative_style_language")
        notes.append("Prompt repeats rule enforcement language that belongs in shared generation policy, not in the shot direction.")

    severity = "fail" if any(
        flag in flags
        for flag in (
            "conceptual_core_not_filmable",
            "abstract_core_without_physical_anchor",
            "severe_pipeline_meta_language",
        )
    ) else "warn" if flags else "pass"
    return flags, notes, core_phrase


def build_suggestions(rows: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    missing_refs = [row for row in rows if row["status"] == "fail" and "missing_reference_for_human_frame" in row["flags"]]
    if missing_refs:
        suggestions.append("Expand subject inference or scene metadata so human-centric frames always receive reference_ids before export.")
    weak_images = [row for row in rows if "low_detail_or_blur" in row["flags"]]
    if weak_images:
        suggestions.append("Tune prompts or regeneration policy for frames flagged low-detail/blur; consider alternate wording or retry pass.")
    duplicate_images = [row for row in rows if "possible_duplicate_image" in row["flags"]]
    if duplicate_images:
        suggestions.append("Strengthen pattern-break logic for adjacent frames with near-duplicate generated imagery.")
    overbound = [row for row in rows if "reference_may_be_unnecessary" in row["flags"]]
    if overbound:
        suggestions.append("Review over-bound frames where references may be attached without a clearly visible recurring person.")
    semantic_failures = [row for row in rows if row["semantic_status"] == "fail"]
    if semantic_failures:
        suggestions.append("Rewrite prompts whose core visual phrase is abstract or meta; every frame should describe a camera-capturable situation, not pipeline intent.")
    qc_leaks = [row for row in rows if "qc_revision_leak" in row["flags"] or "embedded_pipeline_labels" in row["flags"]]
    if qc_leaks:
        suggestions.append("Strip QC notes, visual-function labels, and frame-purpose boilerplate from generator-ready exports.")
    return suggestions


def run_autotest(project_json: Path, run_dir: Path) -> tuple[Path, Path, Path]:
    project = load_project(project_json)
    run_dir = run_dir.resolve()
    image_dir = run_dir / "images"
    if not image_dir.exists():
        raise FileNotFoundError(f"Generated image directory not found: {image_dir}")

    final_scene_plan = load_json(Path(project["prompts"]["final_scene_plan_path"]))
    scenes = final_scene_plan.get("scenes", [])
    subject_registry_payload = load_json(Path(project["prompts"]["subject_registry_path"])) if Path(project["prompts"]["subject_registry_path"]).exists() else {"subjects": []}
    subject_registry = {item["subject_id"]: item for item in subject_registry_payload.get("subjects", [])}
    export_refs = load_export_refs(project)

    rows: list[dict[str, Any]] = []
    previous_hash = ""
    previous_scene_id = ""
    for scene in scenes:
        scene_id = scene["scene_id"]
        image_path = image_dir / f"{scene_id}_V01.png"
        metrics = image_metrics(image_path)
        export_ref_ids = export_refs.get(scene_id, [])
        expected_subject_ids, needs_reference, reference_reason = classify_reference_need(scene, subject_registry, export_ref_ids)
        semantic_flags, semantic_notes, core_phrase = semantic_prompt_audit(scene)
        flags: list[str] = list(semantic_flags)

        if not metrics.get("image_exists"):
            flags.append("missing_generated_image")
        if metrics.get("image_exists"):
            aspect_ratio = float(metrics.get("aspect_ratio", 0.0) or 0.0)
            if abs(aspect_ratio - (16 / 9)) > 0.08:
                flags.append("aspect_ratio_mismatch")
            if float(metrics.get("entropy", 0.0) or 0.0) < 4.2 or float(metrics.get("edge_variance", 0.0) or 0.0) < 350.0:
                flags.append("low_detail_or_blur")
            mean_luma = float(metrics.get("mean_luma", 0.0) or 0.0)
            if mean_luma < 25 or mean_luma > 230:
                flags.append("exposure_outlier")
            current_hash = str(metrics.get("hash", ""))
            if previous_hash and hamming_distance(previous_hash, current_hash) <= 5:
                flags.append("possible_duplicate_image")
            previous_hash = current_hash
            previous_scene_id = scene_id

        expected_ref_ids = []
        for subject_id in expected_subject_ids:
            expected_ref_ids.extend(subject_registry.get(subject_id, {}).get("reference_asset_ids", []))
        if needs_reference and not export_ref_ids:
            flags.append("missing_reference_for_human_frame")
        if not needs_reference and export_ref_ids:
            flags.append("reference_may_be_unnecessary")
        if needs_reference and export_ref_ids:
            expected_subject_set = set(expected_subject_ids)
            export_subject_ids = {
                ref_id.removeprefix("ref_").rsplit("_identity_sheet", 1)[0]
                for ref_id in export_ref_ids
            }
            if not expected_subject_set.issubset(export_subject_ids):
                flags.append("partial_or_wrong_reference_set")

        technical_fail = any(flag in flags for flag in ("missing_generated_image", "missing_reference_for_human_frame", "aspect_ratio_mismatch"))
        semantic_status = "fail" if any(
            flag in semantic_flags
            for flag in (
                "conceptual_core_not_filmable",
                "abstract_core_without_physical_anchor",
                "severe_pipeline_meta_language",
            )
        ) else "warn" if semantic_flags else "pass"
        status = "fail" if technical_fail or semantic_status == "fail" else "warn" if flags else "pass"
        rows.append(
            {
                "scene_id": scene_id,
                "image_path": str(image_path),
                "status": status,
                "flags": flags,
                "expected_subject_ids": expected_subject_ids,
                "needs_reference": needs_reference,
                "export_reference_ids": export_ref_ids,
                "reference_reason": reference_reason,
                "semantic_status": semantic_status,
                "semantic_notes": semantic_notes,
                "core_visual_phrase": core_phrase,
                "width": metrics.get("width"),
                "height": metrics.get("height"),
                "aspect_ratio": metrics.get("aspect_ratio"),
                "entropy": metrics.get("entropy"),
                "mean_luma": metrics.get("mean_luma"),
                "edge_variance": metrics.get("edge_variance"),
                "main_subject": scene.get("director_prompt", {}).get("visual_intent") or scene.get("image_prompt_final", ""),
            }
        )

    suggestions = build_suggestions(rows)
    project_root = Path(project["meta"]["project_root"])
    slug = run_dir.name
    report_dir = project_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{slug}_autotest.json"
    csv_path = report_dir / f"{slug}_autotest.csv"
    md_path = report_dir / f"{slug}_autotest.md"

    save_json(
        json_path,
        {
            "project_id": project["project_id"],
            "run_dir": str(run_dir),
            "summary": {
                "total_frames": len(rows),
                "pass_count": sum(1 for row in rows if row["status"] == "pass"),
                "warn_count": sum(1 for row in rows if row["status"] == "warn"),
                "fail_count": sum(1 for row in rows if row["status"] == "fail"),
            },
            "suggestions": suggestions,
            "frames": rows,
        },
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scene_id",
                "status",
                "flags",
                "expected_subject_ids",
                "needs_reference",
                "export_reference_ids",
                "reference_reason",
                "semantic_status",
                "semantic_notes",
                "core_visual_phrase",
                "width",
                "height",
                "aspect_ratio",
                "entropy",
                "mean_luma",
                "edge_variance",
                "image_path",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "scene_id": row["scene_id"],
                    "status": row["status"],
                    "flags": ",".join(row["flags"]),
                    "expected_subject_ids": ",".join(row["expected_subject_ids"]),
                    "needs_reference": row["needs_reference"],
                    "export_reference_ids": ",".join(row["export_reference_ids"]),
                    "reference_reason": row["reference_reason"],
                    "semantic_status": row["semantic_status"],
                    "semantic_notes": " | ".join(row["semantic_notes"]),
                    "core_visual_phrase": row["core_visual_phrase"],
                    "width": row["width"],
                    "height": row["height"],
                    "aspect_ratio": row["aspect_ratio"],
                    "entropy": row["entropy"],
                    "mean_luma": row["mean_luma"],
                    "edge_variance": row["edge_variance"],
                    "image_path": row["image_path"],
                }
            )

    lines = [
        "# Generated Run Autotest",
        "",
        f"Run directory: {run_dir}",
        f"Total frames: {len(rows)}",
        f"Pass: {sum(1 for row in rows if row['status'] == 'pass')}",
        f"Warn: {sum(1 for row in rows if row['status'] == 'warn')}",
        f"Fail: {sum(1 for row in rows if row['status'] == 'fail')}",
        "",
        "## Suggestions",
    ]
    if suggestions:
        lines.extend([f"- {suggestion}" for suggestion in suggestions])
    else:
        lines.append("- No logic fixes suggested by current heuristics.")
    lines.extend(["", "## Prompt Findings"])
    for row in rows:
        if row["semantic_status"] == "pass":
            continue
        lines.extend(
            [
                f"### {row['scene_id']}",
                f"Semantic status: {row['semantic_status']}",
                f"Core phrase: {row['core_visual_phrase']}",
                f"Flags: {', '.join(row['flags']) if row['flags'] else 'none'}",
                f"Notes: {'; '.join(row['semantic_notes']) if row['semantic_notes'] else 'none'}",
                f"Prompt: {row['main_subject']}",
                "",
            ]
        )
    lines.extend(["## Frame Findings"])
    for row in rows:
        if row["status"] == "pass" and row["semantic_status"] == "pass":
            continue
        lines.extend(
            [
                f"### {row['scene_id']}",
                f"Status: {row['status']}",
                f"Semantic status: {row['semantic_status']}",
                f"Core phrase: {row['core_visual_phrase']}",
                f"Flags: {', '.join(row['flags']) if row['flags'] else 'none'}",
                f"Semantic notes: {'; '.join(row['semantic_notes']) if row['semantic_notes'] else 'none'}",
                f"Reference audit: {row['reference_reason']}",
                f"Expected subjects: {', '.join(row['expected_subject_ids']) if row['expected_subject_ids'] else 'none'}",
                f"Export refs: {', '.join(row['export_reference_ids']) if row['export_reference_ids'] else 'none'}",
                f"Image metrics: {row['width']}x{row['height']}, entropy={row['entropy']}, luma={row['mean_luma']}, edge_variance={row['edge_variance']}",
                "",
            ]
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    project["qc"]["status"] = "autotest_completed"
    project["qc"]["autotest_report_path"] = str(md_path)
    project["qc"]["autotest_json_path"] = str(json_path)
    project["qc"]["autotest_csv_path"] = str(csv_path)
    save_project(project_json, project)
    return json_path, csv_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--run-dir")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    run_dir = discover_run_dir(project, args.run_dir)
    json_path, csv_path, md_path = run_autotest(project_json, run_dir)
    print(json_path)
    print(csv_path)
    print(md_path)


if __name__ == "__main__":
    main()
