import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from yt_nonstop.pipeline.project_status import build_project_status, format_project_status


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SAMPLE_ROOT = ROOT / "sample_projects" / "golden_60s"


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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def seed_calibration_artifacts(project_root: Path, *, with_optional_outputs: bool) -> Path:
    project_json = project_root / "project.json"
    project = json.loads(project_json.read_text(encoding="utf-8"))
    project.setdefault("meta", {})["project_root"] = str(project_root)
    project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for folder in ["planning", "prompts", "qc", "renders", "reports", "logs", "scene_plan", "input", "transcript"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)

    beats = [
        {"beat_id": "beat_0001", "scene_id": "scene_0001", "start": 0.0, "end": 4.0, "duration": 4.0, "voice_text": "Street opens the case.", "visual_priority": "high"},
        {"beat_id": "beat_0002", "scene_id": "scene_0002", "start": 4.0, "end": 8.0, "duration": 4.0, "voice_text": "Receipts create the contradiction.", "visual_priority": "medium"},
        {"beat_id": "beat_0003", "scene_id": "scene_0003", "start": 8.0, "end": 12.0, "duration": 4.0, "voice_text": "The last board isolates the gap.", "visual_priority": "low"},
    ]
    allocation_slots = [
        {
            "visual_slot_id": "VS0001",
            "beat_ids": ["beat_0001"],
            "scene_ids": ["scene_0001"],
            "source_scene_id": "scene_0001",
            "start": 0.0,
            "end": 2.5,
            "duration": 2.5,
            "slot_type": "establishing_shot",
            "generation_decision": "new_image",
            "must_show": ["wet street with evidence van lights"],
            "reason": "Open the film with a concrete location anchor.",
            "film_block_id": "block_a",
        },
        {
            "visual_slot_id": "VS0002",
            "beat_ids": ["beat_0001"],
            "scene_ids": ["scene_0001"],
            "source_scene_id": "scene_0001",
            "start": 2.5,
            "end": 4.0,
            "duration": 1.5,
            "slot_type": "continuation_motion",
            "generation_decision": "hold_previous",
            "must_show": ["same wet street and van lights"],
            "reason": "Continue the opening without cutting away too early.",
            "source_visual_slot_id": "VS0001",
            "film_block_id": "block_a",
        },
        {
            "visual_slot_id": "VS0003",
            "beat_ids": ["beat_0002"],
            "scene_ids": ["scene_0002"],
            "source_scene_id": "scene_0002",
            "start": 4.0,
            "end": 7.7,
            "duration": 3.7,
            "slot_type": "detail_insert",
            "generation_decision": "detail_insert",
            "must_show": ["receipts, timestamps, stopwatch on metal tray"],
            "reason": "Show the exact evidence that creates the timing contradiction.",
            "film_block_id": "block_b",
        },
        {
            "visual_slot_id": "VS0004",
            "beat_ids": ["beat_0002"],
            "scene_ids": ["scene_0002"],
            "source_scene_id": "scene_0002",
            "start": 7.7,
            "end": 8.0,
            "duration": 0.3,
            "slot_type": "detail_insert",
            "generation_decision": "new_angle_same_setup",
            "must_show": ["tension"],
            "reason": "supports narration",
            "source_visual_slot_id": "VS0003",
            "film_block_id": "block_b",
        },
        {
            "visual_slot_id": "VS0005",
            "beat_ids": [],
            "scene_ids": ["scene_0004"],
            "source_scene_id": "scene_0004",
            "start": 12.0,
            "end": 19.5,
            "duration": 7.5,
            "slot_type": "continuation_motion",
            "generation_decision": "continuation_motion",
            "must_show": [],
            "reason": "",
            "source_visual_slot_id": "VS0004",
            "film_block_id": "block_b",
        },
    ]
    shot_plan = {
        "shots": [
            {"shot_id": "shot_0001", "visual_slot_id": "VS0001", "slot_type": "establishing_shot", "generation_decision": "new_image", "importance": "hero", "must_show": ["wet street with evidence van lights"], "film_block_id": "block_a"},
            {"shot_id": "shot_0002", "visual_slot_id": "VS0002", "slot_type": "continuation_motion", "generation_decision": "hold_previous", "importance": "reuse", "must_show": ["same wet street and van lights"], "film_block_id": "block_a"},
            {"shot_id": "shot_0003", "visual_slot_id": "VS0003", "slot_type": "detail_insert", "generation_decision": "detail_insert", "importance": "supporting", "must_show": ["receipts, timestamps, stopwatch on metal tray"], "film_block_id": "block_b"},
            {"shot_id": "shot_0004", "visual_slot_id": "VS0004", "slot_type": "detail_insert", "generation_decision": "new_angle_same_setup", "importance": "supporting", "must_show": ["tension"], "film_block_id": "block_b"},
            {"shot_id": "shot_0005", "visual_slot_id": "VS0005", "slot_type": "continuation_motion", "generation_decision": "continuation_motion", "importance": "reuse", "must_show": [], "film_block_id": "block_b"},
        ],
        "visual_slot_to_shot": {
            "VS0001": {"shot_id": "shot_0001", "source_shot_id": "shot_0001", "variation_note": "Open the film with a concrete location anchor."},
            "VS0002": {"shot_id": "shot_0002", "source_shot_id": "shot_0001", "variation_note": "Continue the opening without cutting away too early."},
            "VS0003": {"shot_id": "shot_0003", "source_shot_id": "shot_0003", "variation_note": "Show the exact evidence that creates the timing contradiction."},
            "VS0004": {"shot_id": "shot_0004", "source_shot_id": "shot_0003", "variation_note": "supports narration"},
            "VS0005": {"shot_id": "shot_0005", "source_shot_id": "shot_0004", "variation_note": ""},
        },
    }
    frame_briefs = [
        {"frame_id": "F0001", "beat_id": "beat_0001", "scene_id": "VS0001", "visual_slot_id": "VS0001", "slot_type": "establishing_shot", "generation_decision": "new_image", "must_show": ["wet street with evidence van lights"], "key_beat": True, "shot_type": "wide establishing shot", "film_block_id": "block_a"},
        {"frame_id": "F0002", "beat_id": "beat_0001", "scene_id": "VS0002", "visual_slot_id": "VS0002", "slot_type": "continuation_motion", "generation_decision": "hold_previous", "must_show": ["same wet street and van lights"], "key_beat": False, "shot_type": "continuation motion hold", "film_block_id": "block_a"},
        {"frame_id": "F0003", "beat_id": "beat_0002", "scene_id": "VS0003", "visual_slot_id": "VS0003", "slot_type": "detail_insert", "generation_decision": "detail_insert", "must_show": ["receipts, timestamps, stopwatch on metal tray"], "key_beat": True, "shot_type": "close detail insert", "film_block_id": "block_b"},
        {"frame_id": "F0004", "beat_id": "beat_0002", "scene_id": "VS0004", "visual_slot_id": "VS0004", "slot_type": "detail_insert", "generation_decision": "new_angle_same_setup", "must_show": ["tension"], "key_beat": False, "shot_type": "close detail insert", "film_block_id": "block_b"},
        {"frame_id": "F0005", "beat_id": "", "scene_id": "VS0005", "visual_slot_id": "VS0005", "slot_type": "continuation_motion", "generation_decision": "continuation_motion", "must_show": [], "key_beat": False, "shot_type": "continuation motion hold", "film_block_id": "block_b"},
    ]

    write_json(project_root / "planning" / "narration_beats.json", {"beats": beats})
    write_json(
        project_root / "planning" / "visual_allocation_plan.json",
        {
            "visual_slots": allocation_slots,
            "metrics": {
                "narration_beats_count": 3,
                "visual_slots_count": 5,
                "new_image_slots_count": 3,
                "hold_or_continuation_slots_count": 2,
                "planned_variants_count": 3,
                "average_slot_duration": 3.1,
            },
        },
    )
    write_json(project_root / "prompts" / "visual_shot_plan.json", shot_plan)
    write_json(project_root / "planning" / "frame_briefs.json", frame_briefs)

    if with_optional_outputs:
        write_json(project_root / "renders" / "edit_decision_list.json", {"edl": [{"visual_slot_id": "VS0005", "motion_type": "static_hold"}]})
        write_json(project_root / "reports" / "production_report.json", {"status": "needs_review"})
        write_json(project_root / "qc" / "continuity_qc_report.json", {"warnings": ["camera drift"], "errors": ["identity mismatch"]})
        write_json(project_root / "qc" / "review_decisions.json", {"decisions": [{"visual_slot_id": "VS0005", "status": "reject", "reason": "drops out of beat coverage"}]})
    return project_json


def test_visual_calibration_report_runs_on_golden_sample_and_status_mentions_it(tmp_path):
    project_root = tmp_path / "golden_60s"
    shutil.copytree(SAMPLE_ROOT, project_root)
    project_json = seed_calibration_artifacts(project_root, with_optional_outputs=True)

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_visual_calibration_report.py"), "--project-json", str(project_json)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=cli_env(),
    )

    report_json = project_root / "reports" / "visual_calibration_report.json"
    report_md = project_root / "reports" / "visual_calibration_report.md"
    assert report_json.exists()
    assert report_md.exists()
    assert str(report_json) in result.stdout

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["metrics"]["narration_beats_count"] == 3
    assert payload["metrics"]["visual_slots_count"] == 5
    assert payload["metrics"]["beats_with_no_visual_slots"] == 1
    assert payload["metrics"]["long_static_holds"] == 1
    assert payload["metrics"]["very_short_slots"] == 1
    assert payload["metrics"]["slots_with_missing_must_show"] == 1
    assert payload["metrics"]["slots_with_abstract_or_weak_must_show"] >= 1
    assert payload["metrics"]["slots_with_empty_or_generic_reason"] >= 2
    assert payload["metrics"]["slots_excluded_by_review"] == 1
    assert payload["metrics"]["continuity_errors"] == 1
    assert "Project status command:" in report_md.read_text(encoding="utf-8")

    status = build_project_status(project_json)
    formatted = format_project_status(status)
    assert "visual calibration report available:" in formatted


def test_visual_calibration_report_runs_on_bootstrapped_real_pilot_before_image_generation(tmp_path):
    source_srt = tmp_path / "pilot_source.srt"
    source_srt.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nA corridor opens the reconstruction.\n\n"
        "2\n00:00:05,000 --> 00:00:10,000\nA tray of receipts narrows the timeline.\n",
        encoding="utf-8",
    )
    bootstrap_root = tmp_path / "real_pilot_project"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "bootstrap_real_pilot_project.py"),
            "--project-root",
            str(bootstrap_root),
            "--source-srt",
            str(source_srt),
            "--profile",
            "no_vlm_production",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=cli_env(),
    )
    project_json = seed_calibration_artifacts(bootstrap_root, with_optional_outputs=False)

    subprocess.run(
        [sys.executable, str(SCRIPTS / "build_visual_calibration_report.py"), "--project-json", str(project_json)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=cli_env(),
    )

    payload = json.loads((bootstrap_root / "reports" / "visual_calibration_report.json").read_text(encoding="utf-8"))
    assert payload["metrics"]["visual_slots_count"] == 5
    assert payload["metrics"]["slots_excluded_by_review"] == 0
    assert payload["production_report_status"] is None
