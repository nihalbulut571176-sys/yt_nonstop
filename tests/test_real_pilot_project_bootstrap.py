import json
import os
import subprocess
import sys
from pathlib import Path

from yt_nonstop.pipeline.project_config import load_project


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bootstrap_real_pilot_project.py"


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    extra = [str(ROOT / "src"), str(ROOT / "scripts")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(extra + ([existing] if existing else []))
    for key in [
        "OPENAI_API_KEY",
        "FASTGEN_API_KEY",
        "HEYGEN_API_KEY",
        "VEONONSTOP_API_KEY",
        "YT_NONSTOP_LLM_PROVIDER_MODE",
        "YT_NONSTOP_BEAT_AUTHORING_PROVIDER",
        "YT_NONSTOP_VISUAL_ALLOCATION_PROVIDER",
        "YT_NONSTOP_IMAGE_SEMANTIC_QC_MODE",
    ]:
        env.pop(key, None)
    return env


def test_bootstrap_real_pilot_project_and_status(tmp_path):
    source_srt = tmp_path / "source.srt"
    source_srt.write_text(
        "\n\n".join(
            [
                "1\n00:00:00,000 --> 00:00:04,000\nA quiet street opens the investigation.",
                "2\n00:00:04,000 --> 00:00:08,500\nReceipts and timestamps show the first contradiction.",
                "3\n00:00:08,500 --> 00:00:13,000\nThe narrator marks the route toward the back entrance.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    source_audio = tmp_path / "narration.mp3"
    source_audio.write_bytes(b"fake audio bytes for bootstrap only")
    project_root = tmp_path / "real_pilot_project"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project_root),
            "--source-srt",
            str(source_srt),
            "--source-audio",
            str(source_audio),
            "--profile",
            "no_vlm_production",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=cli_env(),
    )

    project_json = project_root / "project.json"
    assert project_json.exists()
    assert (project_root / "input" / "source.srt").exists()
    assert (project_root / "input" / "source_audio.mp3").exists()
    assert (project_root / "transcript" / "raw_whisper.srt").exists()
    assert (project_root / "transcript" / "cleaned.srt").exists()
    assert f'yt-nonstop run --project-json "{project_json}" --to production_report' in result.stdout
    assert f'yt-nonstop status --project-json "{project_json}"' in result.stdout

    project = load_project(project_json)
    assert project["workflow"]["profile"] == "no_vlm_production"
    assert project["workflow"]["render_dry_run"] is True
    assert project["providers"]["llm_provider"]["mode"] == "disabled"
    assert project["planning"]["visual_allocation_provider"] == "disabled"
    assert project["qc"]["image_semantic_qc_mode"] == "disabled"
    assert project["images"]["provider"] == "disabled"
    assert project["scene_plan"]["source_srt_path"].endswith("transcript\\cleaned.srt") or project["scene_plan"]["source_srt_path"].endswith("transcript/cleaned.srt")

    status_result = subprocess.run(
        [sys.executable, "-m", "yt_nonstop.cli", "status", "--project-json", str(project_json), "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=cli_env(),
    )
    status_payload = json.loads(status_result.stdout)
    assert status_payload["project_id"] == "real_pilot_project"
    assert "next_command" in status_payload
