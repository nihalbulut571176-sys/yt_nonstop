import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from yt_nonstop.pipeline.project_status import build_project_status


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    extra = [str(ROOT / "src"), str(ROOT / "scripts")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(extra + ([existing] if existing else []))
    return env


def build_project_fixture(tmp_root: Path, *, allow_manual_review_without_vlm: bool) -> Path:
    project_root = tmp_root / "project"
    for folder in ["exports", "prompts", "qc", "renders", "logs"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    image_path = project_root / "renders" / "frame.png"
    image_path.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
        "0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082"
    ))
    project = {
        "project_id": "review_policy_smoke",
        "meta": {"project_root": str(project_root)},
        "inputs": {"audio_duration_seconds": 1.0},
        "workflow": {"profile": "review_policy"},
        "qc": {
            "allow_manual_review_without_vlm": allow_manual_review_without_vlm,
            "review_decisions_path": str(project_root / "qc" / "review_decisions.json"),
            "review_applied_manifest_path": str(project_root / "qc" / "review_applied_manifest.json"),
            "regeneration_plan_path": str(project_root / "qc" / "regeneration_plan.json"),
            "continuity_qc_report_path": str(project_root / "qc" / "continuity_qc_report.json"),
        },
        "images": {
            "selected_images_manifest_path": str(project_root / "qc" / "selected_images_manifest.json"),
            "image_qc_report_path": str(project_root / "qc" / "image_qc_report.json"),
        },
        "exports": {"montage_timing_map_json_path": str(project_root / "exports" / "montage_timing_map.json")},
        "prompts": {"final_scene_plan_path": str(project_root / "prompts" / "final_scene_plan.json")},
        "render": {
            "edit_decision_list_path": str(project_root / "renders" / "edit_decision_list.json"),
            "render_report_json_path": str(project_root / "logs" / "render_report.json"),
        },
    }
    write_json(project_root / "project.json", project)
    write_json(project_root / "exports" / "montage_timing_map.json", [])
    write_json(
        project_root / "prompts" / "final_scene_plan.json",
        {"scenes": [{"scene_id": "scene_0001", "frame_id": "F0001", "beat_id": "beat_0001", "shot_index": 1, "start": 0.0, "end": 1.0, "voice_text": "voice", "render_asset_path": str(image_path), "still_image_path": str(image_path), "visualized_claim": "claim"}]},
    )
    write_json(project_root / "qc" / "continuity_qc_report.json", {"warnings": [], "errors": []})
    write_json(project_root / "qc" / "image_qc_report.json", {"images": [{"scene_id": "scene_0001"}]})
    write_json(
        project_root / "qc" / "selected_images_manifest.json",
        {"selected_images": [{"scene_id": "scene_0001", "frame_id": "F0001", "beat_id": "beat_0001", "voice_text": "voice", "visualized_claim": "claim", "selection_status": "manual_review", "coverage_status": "pass", "selected_image_path": str(image_path)}]},
    )
    write_json(project_root / "qc" / "regeneration_plan.json", {"tasks": []})
    write_json(project_root / "logs" / "render_report.json", {"status": "pending"})
    return project_root / "project.json"


def test_timeline_blocks_manual_review_when_policy_disallows():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp), allow_manual_review_without_vlm=False)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_project_slideshow_timeline.py"), "--project-json", str(project_json)],
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        assert result.returncode != 0
        assert "not timeline-eligible" in (result.stderr or result.stdout)


def test_timeline_allows_manual_review_when_semantic_qc_disabled_and_policy_allows():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp), allow_manual_review_without_vlm=True)
        project_root = project_json.parent
        project = json.loads(project_json.read_text(encoding="utf-8"))
        project["qc"]["image_semantic_qc_mode"] = "disabled"
        write_json(project_json, project)
        write_json(
            project_root / "qc" / "selected_images_manifest.json",
            {
                "selected_images": [
                    {
                        "scene_id": "scene_0001",
                        "frame_id": "F0001",
                        "beat_id": "beat_0001",
                        "voice_text": "voice",
                        "visualized_claim": "claim",
                        "selection_status": "manual_review",
                        "coverage_status": "fail",
                        "selected_image_path": str(project_root / "renders" / "frame.png"),
                    }
                ]
            },
        )
        subprocess.run(
            [sys.executable, str(SCRIPTS / "build_project_slideshow_timeline.py"), "--project-json", str(project_json)],
            check=True,
            timeout=30,
            env=cli_env(),
        )
        assert (project_root / "renders" / "edit_decision_list.json").exists()


def test_production_report_and_dashboard_block_regeneration_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp), allow_manual_review_without_vlm=True)
        project_root = project_json.parent
        write_json(
            project_root / "qc" / "regeneration_plan.json",
            {"tasks": [{"scene_id": "scene_0001", "action": "rewrite_prompt_and_regenerate", "status": "queued"}]},
        )
        subprocess.run(
            [sys.executable, str(SCRIPTS / "build_production_report.py"), "--project-json", str(project_json)],
            check=True,
            timeout=30,
            env=cli_env(),
        )
        report = json.loads((project_root / "reports" / "production_report.json").read_text(encoding="utf-8"))
        assert report["status"] == "blocked"
        dashboard = build_project_status(project_json)
        assert any("regeneration/review task" in item for item in dashboard.blocked)


def test_regeneration_plan_skips_semantic_only_manual_review_when_disabled_and_approved():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp), allow_manual_review_without_vlm=True)
        project_root = project_json.parent
        project = json.loads(project_json.read_text(encoding="utf-8"))
        project["workflow"]["profile"] = "technical_fastgen_pilot"
        project["qc"]["image_semantic_qc_mode"] = "disabled"
        write_json(project_json, project)
        write_json(
            project_root / "qc" / "selected_images_manifest.json",
            {
                "selected_images": [
                    {
                        "scene_id": "scene_0001",
                        "frame_id": "F0001",
                        "beat_id": "beat_0001",
                        "voice_text": "voice",
                        "visualized_claim": "claim",
                        "selection_status": "use",
                        "selection_status_before_human_review": "manual_review",
                        "human_review_status": "approve",
                        "coverage_status": "fail",
                        "semantic_flags": ["must_show_not_grounded_in_prompt"],
                        "selected_image_path": str(project_root / "renders" / "frame.png"),
                    }
                ]
            },
        )
        subprocess.run(
            [sys.executable, str(SCRIPTS / "build_regeneration_plan.py"), "--project-json", str(project_json)],
            check=True,
            timeout=30,
            env=cli_env(),
        )
        plan = json.loads((project_root / "qc" / "regeneration_plan.json").read_text(encoding="utf-8"))
        assert plan["accepted_count"] == 1
        assert plan["needs_action_count"] == 0
        assert plan["tasks"] == []


def test_cli_review_runs_apply_and_reports_blockers():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp), allow_manual_review_without_vlm=False)
        project_root = project_json.parent
        write_json(project_root / "qc" / "review_decisions.json", {"decisions": [{"scene_id": "scene_0001", "status": "reject"}]})
        result = subprocess.run(
            [sys.executable, "-m", "yt_nonstop.cli", "review", "--project-json", str(project_json)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        assert "BLOCKED:" in result.stdout
        assert "exclude render" in result.stdout or "manual review item" in result.stdout
