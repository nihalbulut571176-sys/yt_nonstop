import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from yt_nonstop.pipeline.orchestrator import compute_stage_input_hash, compute_stage_output_hash
from yt_nonstop.pipeline.project_config import load_project
from yt_nonstop.state.pipeline_state import (
    connect as connect_state_db,
    get_stage_state,
    mark_stage_completed,
    mark_stage_running,
    resolve_stale_stages,
    resolve_state_db_path,
)


ROOT = Path(__file__).resolve().parents[1]
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082"
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    extra = [str(ROOT / "src"), str(ROOT / "scripts")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(extra + ([existing] if existing else []))
    return env


def build_project_fixture(tmp_root: Path) -> Path:
    project_root = tmp_root / "project"
    for folder in ["planning", "prompts", "images/run", "logs", "qc", "renders", "scene_plan", "transcript", "exports"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    project = json.loads((ROOT / "deliverables" / "project.template.json").read_text(encoding="utf-8"))
    project["project_id"] = "cli_resume_smoke"
    project["meta"]["project_root"] = str(project_root)
    project["current_stage"] = "build_narration_beats"
    project["inputs"]["audio_duration_seconds"] = 4.0
    project.setdefault("planning", {})["narration_beats_status"] = "skeleton_built"

    narration_beats_path = project_root / "planning" / "narration_beats.json"
    write_json(
        narration_beats_path,
        {
            "beats": [
                {
                    "beat_id": "beat_0001",
                    "scene_id": "scene_0001",
                    "start": 0.0,
                    "end": 4.0,
                    "duration": 4.0,
                    "voice_text": "A forensic board explains the route.",
                    "spoken_claim": "forensic board explains the route",
                    "must_visualize": ["forensic board with marked route"],
                    "entity_mentions": [],
                    "location_mentions": [],
                    "beat_role": "explanation",
                    "visual_priority": "high",
                }
            ]
        },
    )
    visual_shot_plan_path = project_root / "prompts" / "visual_shot_plan.json"
    write_json(
        visual_shot_plan_path,
        {
            "shots": [
                {
                    "shot_id": "shot_0001",
                    "beat_ids": ["beat_0001"],
                    "film_block_id": "block_a",
                    "generation_mode": "unique",
                    "shot_type": "medium shot",
                    "visual_function": "evidence",
                    "must_show": ["forensic board with marked route"],
                    "camera": "stable documentary camera",
                    "lighting": "soft practical light",
                    "transition_in": "cut",
                    "transition_out": "cut",
                }
            ]
        },
    )
    image_path = project_root / "images" / "run" / "frame_0001.png"
    image_path.write_bytes(TINY_PNG)
    write_json(
        project_root / "images" / "run" / "run_manifest.json",
        {
            "job_id": "job_cli_resume_smoke",
            "completed_count": 1,
            "failed_count": 0,
            "missing_count": 0,
            "generated_images": [
                {
                    "job_id": "job_cli_resume_smoke",
                    "scene_id": "scene_0001",
                    "frame_id": "F0001",
                    "source_prompt_index": 1,
                    "prompt_hash": "hash_cli_resume_smoke",
                    "generator_profile": "fastgen_stub",
                    "created_at": "2026-05-28T00:00:00Z",
                    "status": "success",
                    "image_path": str(image_path),
                }
            ],
        },
    )
    write_json(
        project_root / "qc" / "image_qc_report.json",
        {"selected_images": [{"frame_id": "F0001", "coverage_status": "pass", "selection_status": "use"}]},
    )
    write_json(
        project_root / "qc" / "selected_images_manifest.json",
        {"selected_images": [{"frame_id": "F0001", "selection_status": "use", "selected_image_path": str(image_path)}]},
    )
    (project_root / "images" / "run").mkdir(parents=True, exist_ok=True)
    project_json = project_root / "project.json"
    write_json(project_json, project)
    return project_json


def test_stage_state_marks_downstream_stale_when_input_hash_changes():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp))
        project = load_project(project_json)
        state_db = resolve_state_db_path(project_json, project)
        conn = connect_state_db(state_db)
        try:
            mark_stage_running(conn, project_id="cli_resume_smoke", stage_name="build_narration_beats", input_hash="old")
            mark_stage_completed(conn, project_id="cli_resume_smoke", stage_name="build_narration_beats", input_hash="old", output_hash="out-a")
            mark_stage_completed(conn, project_id="cli_resume_smoke", stage_name="build_visual_shot_plan", input_hash="old-b", output_hash="out-b")
            stale = resolve_stale_stages(
                conn,
                project_id="cli_resume_smoke",
                ordered_stage_hashes=[
                    {"stage_name": "build_narration_beats", "input_hash": "new", "output_hash": "out-a", "output_exists": True},
                    {"stage_name": "build_visual_shot_plan", "input_hash": "old-b", "output_hash": "out-b", "output_exists": True},
                ],
            )
            assert stale == ["build_narration_beats", "build_visual_shot_plan"]
            assert get_stage_state(conn, project_id="cli_resume_smoke", stage_name="build_visual_shot_plan").status == "stale"
        finally:
            conn.close()


def test_cli_status_and_validate_commands_work():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp))
        status_result = subprocess.run(
            [sys.executable, "-m", "yt_nonstop.cli", "status", "--project-json", str(project_json), "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        payload = json.loads(status_result.stdout)
        assert payload["project_id"] == "cli_resume_smoke"
        assert "next_command" in payload

        validate_result = subprocess.run(
            [sys.executable, "-m", "yt_nonstop.cli", "validate", "--project-json", str(project_json), "--stage", "images"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        report = json.loads(validate_result.stdout)
        assert report["status"] == "passed"


def test_cli_run_resume_skips_completed_fresh_stage():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp))
        project = load_project(project_json)
        state_db = resolve_state_db_path(project_json, project)
        conn = connect_state_db(state_db)
        try:
            input_hash = compute_stage_input_hash(project_json, project, "build_narration_beats")
            output_hash, _ = compute_stage_output_hash(project, "build_narration_beats")
            mark_stage_completed(
                conn,
                project_id="cli_resume_smoke",
                stage_name="build_narration_beats",
                input_hash=input_hash,
                output_hash=output_hash,
            )
        finally:
            conn.close()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "yt_nonstop.cli",
                "run",
                "--project-json",
                str(project_json),
                "--from",
                "build_narration_beats",
                "--to",
                "build_narration_beats",
                "--resume",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        assert "SKIP: build_narration_beats (completed and fresh)" in result.stdout
