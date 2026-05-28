from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Protocol

from llm_pipeline_contracts import inspect_image_file
from prompt_safety import is_probably_abstract, lint_prompt_observability

try:
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover
    Image = None
    ImageFilter = None


class ImageSemanticQCAdapter(Protocol):
    def evaluate(
        self,
        image_path: Path,
        beat_context: dict[str, Any],
        reference_ids: list[str],
        neighbor_contexts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ...


def clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def image_metrics(image_path: Path) -> dict[str, Any]:
    inspection = inspect_image_file(image_path)
    metrics: dict[str, Any] = {"inspection": inspection}
    if Image is None or not inspection.get("exists"):
        return metrics
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            histogram = gray.histogram()
            total = sum(histogram) or 1
            entropy = 0.0
            for count in histogram:
                if count <= 0:
                    continue
                probability = count / total
                entropy -= probability * math.log2(probability)
            metrics["entropy"] = round(entropy, 4)
            if ImageFilter is not None:
                edges = gray.filter(ImageFilter.FIND_EDGES)
                edge_hist = edges.histogram()
                edge_total = sum(edge_hist) or 1
                edge_mean = sum(index * count for index, count in enumerate(edge_hist)) / edge_total
                metrics["edge_mean"] = round(edge_mean, 2)
    except Exception as exc:  # pragma: no cover
        metrics["error"] = str(exc)
    return metrics


def assess_prompt_semantics(beat_context: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    must_show = [clean_text(item) for item in beat_context.get("must_show", []) if clean_text(item)]
    visualized_claim = clean_text(beat_context.get("visualized_claim", ""))
    semantic_flags: list[str] = []
    coverage_rows = []
    for item in must_show:
        warnings = lint_prompt_observability(item, what_is_in_frame=item)
        status = "present"
        if is_probably_abstract(item):
            status = "uncertain"
            semantic_flags.append("abstract_must_show")
        elif len(warnings) >= 3:
            status = "uncertain"
            semantic_flags.append("weak_must_show_observability")
        coverage_rows.append({"item": item, "status": status})
    if not must_show:
        semantic_flags.append("missing_must_show")
    if not visualized_claim:
        semantic_flags.append("missing_visualized_claim")
    elif is_probably_abstract(visualized_claim):
        semantic_flags.append("abstract_visualized_claim")
    return coverage_rows, semantic_flags


class HeuristicImageSemanticQCAdapter:
    provider_name = "heuristic_image_semantic_qc_v1"

    def evaluate(
        self,
        image_path: Path,
        beat_context: dict[str, Any],
        reference_ids: list[str],
        neighbor_contexts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        metrics = image_metrics(image_path)
        inspection = metrics.get("inspection", {})
        must_show_coverage, semantic_flags = assess_prompt_semantics(beat_context)
        if not inspection.get("exists"):
            semantic_flags.append("missing_image_file")
        elif not inspection.get("readable"):
            semantic_flags.append("unreadable_image_file")
        if metrics.get("entropy") is not None and float(metrics["entropy"]) < 3.5:
            semantic_flags.append("low_visual_entropy")
        if metrics.get("edge_mean") is not None and float(metrics["edge_mean"]) < 6.0:
            semantic_flags.append("low_edge_energy")

        required_refs = list(reference_ids or [])
        identity_status = "pass" if not required_refs or inspection.get("exists") else "fail"
        if required_refs and not inspection.get("exists"):
            semantic_flags.append("missing_identity_reference_target")

        style_status = "pass"
        if neighbor_contexts:
            current_block = clean_text(beat_context.get("film_block_id", ""))
            neighbor_blocks = {clean_text(item.get("film_block_id", "")) for item in neighbor_contexts if clean_text(item.get("film_block_id", ""))}
            if current_block and neighbor_blocks and current_block not in neighbor_blocks:
                style_status = "uncertain"

        decision = "use"
        if any(flag in semantic_flags for flag in {"missing_image_file", "unreadable_image_file"}):
            decision = "reject"
        elif any(flag in semantic_flags for flag in {"abstract_must_show", "abstract_visualized_claim"}):
            decision = "manual_review"
        elif any(row["status"] != "present" for row in must_show_coverage):
            decision = "manual_review"

        return {
            "provider": self.provider_name,
            "vlm_caption": clean_text(
                f"{inspection.get('format') or 'image'} {inspection.get('width') or '?'}x{inspection.get('height') or '?'} "
                f"interpreted against beat claim: {beat_context.get('visualized_claim', '')}"
            ),
            "must_show_coverage": must_show_coverage,
            "identity_check": {
                "required_reference_ids": required_refs,
                "status": identity_status,
            },
            "style_continuity_check": {
                "status": style_status,
            },
            "coverage_status": "pass" if decision in {"use", "manual_review"} and not any(flag in semantic_flags for flag in {"missing_image_file", "unreadable_image_file"}) else "fail",
            "decision": decision,
            "semantic_flags": sorted(set(semantic_flags)),
            "technical_qc_passed": bool(inspection.get("exists") and inspection.get("readable")),
        }


def default_image_semantic_qc_adapter() -> ImageSemanticQCAdapter:
    return HeuristicImageSemanticQCAdapter()
