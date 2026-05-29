import json
from pathlib import Path

from yt_nonstop.pipeline.project_status import build_project_status, format_project_status
from yt_nonstop.state.pipeline_state import connect as connect_state_db
from yt_nonstop.state.pipeline_state import mark_frame_failed, resolve_state_db_path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_project_status_dashboard_reads_artifacts_and_sqlite_state(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = json.loads((ROOT / "deliverables" / "project.template.json").read_text(encoding="utf-8"))
    project["project_id"] = "dashboard_smoke"
    project["meta"]["project_root"] = str(project_root)
    project["current_stage"] = "human_review"
    project["workflow"] = {"profile": "no_vlm_production"}
    project.setdefault("render", {})["status"] = "pending"

    project_json = project_root / "project.json"
    write_json(project_json, project)

    # load_project normalizes template paths under project_root; mirror those defaults.
    planning = project_root / "planning"
    qc = project_root / "qc"
    images = project_root / "images" / "run"
    renders = project_root / "renders"
    logs = project_root / "logs"
    write_json(planning / "narration_beats.json", {"beats": [{"beat_id": "B1"}, {"beat_id": "B2"}]})
    write_json(
        planning / "visual_allocation_plan.json",
        {
            "visual_slots": [
                {"visual_slot_id": "VS1", "generation_decision": "new_image", "variant_count": 2},
                {"visual_slot_id": "VS2", "generation_decision": "detail_insert", "variant_count": 1},
                {"visual_slot_id": "VS3", "generation_decision": "hold_previous", "variant_count": 0},
            ],
            "metrics": {
                "narration_beats_count": 2,
                "visual_slots_count": 3,
                "new_image_slots_count": 2,
                "hold_or_continuation_slots_count": 1,
                "planned_variants_count": 3,
            },
        },
    )
    write_json(
        images / "run_manifest.json",
        {"generated_images": [{"frame_id": "F1", "status": "success"}, {"frame_id": "F2", "status": "failed"}]},
    )
    write_json(
        qc / "selected_images_manifest.json",
        {
            "selected_images": [
                {"scene_id": "S1", "selection_status": "use"},
                {"scene_id": "S2", "selection_status": "manual_review"},
                {"scene_id": "S3", "selection_status": "reject", "render_excluded": True},
            ]
        },
    )
    write_json(qc / "continuity_qc_report.json", {"warnings": ["camera shift"], "errors": []})
    write_json(renders / "edit_decision_list.json", {"edl": []})
    write_json(logs / "render_report.json", {"status": "pending"})

    state_db = resolve_state_db_path(project_json, project)
    conn = connect_state_db(state_db)
    try:
        mark_frame_failed(
            conn,
            project_id="dashboard_smoke",
            frame_id="F0002",
            visual_slot_id="VS0002",
            error_message="synthetic failure",
        )
    finally:
        conn.close()

    dashboard = build_project_status(project_json)
    assert dashboard.narration_beats_count == 2
    assert dashboard.visual_slots_count == 3
    assert dashboard.new_image_slots_count == 2
    assert dashboard.hold_slots_count == 1
    assert dashboard.planned_variants_count == 3
    assert dashboard.generated_images_success == 1
    assert dashboard.manual_review_count == 1
    assert dashboard.rejected_or_excluded_count == 1
    assert dashboard.failed_frames_count == 1
    assert dashboard.continuity_warnings_count == 1

    text = format_project_status(dashboard, include_failed=True)
    assert "visual slots: 3" in text
    assert "failed frames: 1" in text
    assert "Next actions:" in text
