import base64
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from yt_nonstop.providers.vlm_semantic_qc_provider import (  # noqa: E402
    VLMProviderNotConfiguredError,
    default_image_semantic_qc_adapter,
    normalize_provider_semantic_result,
)


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9uoAAAAASUVORK5CYII="
)


def write_png(path: Path) -> None:
    path.write_bytes(TINY_PNG)


def test_heuristic_is_default_and_reports_caption_and_must_show_coverage(tmp_path):
    image_path = tmp_path / "frame.png"
    write_png(image_path)
    adapter = default_image_semantic_qc_adapter({})

    result = adapter.evaluate(
        image_path=image_path,
        beat_context={
            "voice_text": "The investigators trace the route.",
            "visualized_claim": "route reconstruction",
            "must_show": ["forensic map", "red route pins"],
        },
        reference_ids=[],
        neighbor_contexts=[],
    )

    assert adapter.provider_name == "heuristic_image_semantic_qc_v1"
    assert result["semantic_qc_mode"] == "heuristic"
    assert result["vlm_caption"]
    assert [row["item"] for row in result["must_show_coverage"]] == ["forensic map", "red route pins"]


def test_external_mode_fails_fast_without_configured_vlm():
    with pytest.raises(VLMProviderNotConfiguredError):
        default_image_semantic_qc_adapter(
            {
                "qc": {
                    "image_semantic_qc_mode": "external",
                    "image_semantic_qc_provider": "external",
                }
            }
        )


def test_provider_normalization_backfills_coverage_for_every_must_show(tmp_path):
    image_path = tmp_path / "frame.png"
    write_png(image_path)

    result = normalize_provider_semantic_result(
        payload={
            "vlm_caption": "A forensic board with route evidence.",
            "must_show_coverage": [
                {"item": "forensic map", "status": "present", "evidence": "map visible"},
            ],
            "coverage_status": "pass",
            "decision": "use",
            "semantic_flags": [],
        },
        provider_name="fake_vlm",
        image_path=image_path,
        beat_context={"must_show": ["forensic map", "red route pins"]},
        reference_ids=[],
    )

    assert [row["item"] for row in result["must_show_coverage"]] == ["forensic map", "red route pins"]
    assert result["must_show_coverage"][1]["status"] == "uncertain"
    assert result["provider"] == "fake_vlm"
