import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pipeline_contracts import stable_hash
from yt_nonstop.pipeline import real_generation_preflight as preflight_module
from yt_nonstop.pipeline.pilot_profiles import apply_runtime_profile, effective_limit_frames
from yt_nonstop.state.pipeline_state import connect as connect_state_db
from yt_nonstop.state.pipeline_state import mark_frame_failed, mark_frame_success, resolve_state_db_path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from llm_pipeline_contracts import compute_prompt_hash  # noqa: E402
from run_project_fastgen_generation import select_generation_items  # noqa: E402


TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082"
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in [
        "OPENAI_API_KEY",
        "FAST_GEN_API_KEY",
        "HEYGEN_API_KEY",
        "VEONONSTOP_API_KEY",
        "YT_NONSTOP_BEAT_AUTHORING_PROVIDER",
        "YT_NONSTOP_VISUAL_ALLOCATION_PROVIDER",
        "YT_NONSTOP_IMAGE_SEMANTIC_QC_MODE",
        "YT_NONSTOP_LLM_PROVIDER_MODE",
        "YT_NONSTOP_LLM_PROVIDER_COMMAND",
    ]:
        env.pop(key, None)
    extra = [str(ROOT / "src"), str(ROOT / "scripts")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(extra + ([existing] if existing else []))
    return env


def build_pilot_fixture(tmp_root: Path) -> Path:
    project_root = tmp_root / "project"
    for folder in [
        "audio",
        "planning",
        "prompts",
        "scene_plan",
        "exports",
        "reports",
        "logs",
        "qc",
        "renders",
        Path("images") / "run",
    ]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)

    project = json.loads((ROOT / "deliverables" / "project.template.json").read_text(encoding="utf-8"))
    project["project_id"] = "technical_fastgen_pilot_smoke"
    project["profile_id"] = "technical_fastgen_pilot"
    project["meta"]["project_root"] = str(project_root)
    project["current_stage"] = "export_generation_batches"
    project.setdefault("workflow", {})
    project["workflow"]["profile"] = "technical_fastgen_pilot"
    project["workflow"]["render_dry_run"] = True
    project.setdefault("qc", {})
    project["qc"]["allow_manual_review_without_vlm"] = True
    project["qc"]["image_semantic_qc_mode"] = "disabled"

    audio_path = project_root / "audio" / "pilot_audio.mp3"
    audio_path.write_bytes(b"pilot audio")
    project["inputs"]["audio_path"] = str(audio_path)
    project["inputs"]["audio_duration_seconds"] = 16.0

    project["planning"]["visual_allocation_plan_path"] = str(project_root / "planning" / "visual_allocation_plan.json")
    project["planning"]["narration_beats_path"] = str(project_root / "planning" / "narration_beats.json")
    project["prompts"]["fastgen_export_path"] = str(project_root / "exports" / "fastgen_prompts.md")
    project["prompts"]["generator_ready_path"] = str(project_root / "exports" / "fastgen_prompts.md")
    project["prompts"]["prompt_package_path"] = str(project_root / "prompts" / "prompt_package.json")
    project["prompts"]["final_scene_plan_path"] = str(project_root / "scene_plan" / "final_scene_plan.json")
    project["prompts"]["reference_mapping_path"] = str(project_root / "prompts" / "fastgen_ref_paths.json")
    project["scene_plan"]["scene_plan_path"] = str(project_root / "scene_plan" / "scene_plan.json")
    project["exports"]["montage_timing_map_json_path"] = str(project_root / "exports" / "montage_timing_map.json")
    project["images"]["run_manifest_path"] = str(project_root / "images" / "run" / "run_manifest.json")
    project["images"]["raw_images_dir"] = str(project_root / "images" / "run")
    project["images"]["normalized_images_dir"] = str(project_root / "images" / "run")
    project["images"]["image_qc_report_path"] = str(project_root / "qc" / "image_qc_report.json")
    project["images"]["selected_images_manifest_path"] = str(project_root / "qc" / "selected_images_manifest.json")
    project["qc"]["regeneration_plan_path"] = str(project_root / "qc" / "regeneration_plan.json")
    project["qc"]["continuity_qc_report_path"] = str(project_root / "qc" / "continuity_qc_report.json")
    project["qc"]["review_package_html_path"] = str(project_root / "qc" / "review_package.html")
    project["qc"]["review_decisions_path"] = str(project_root / "qc" / "review_decisions.json")
    project["reports"]["visual_calibration_report_json_path"] = str(project_root / "reports" / "visual_calibration_report.json")
    project["reports"]["visual_calibration_report_md_path"] = str(project_root / "reports" / "visual_calibration_report.md")
    project["reports"]["production_report_json_path"] = str(project_root / "reports" / "production_report.json")
    project["reports"]["production_report_md_path"] = str(project_root / "reports" / "production_report.md")
    project["render"]["ffconcat_path"] = str(project_root / "renders" / "timeline.ffconcat")
    project["render"]["timeline_json_path"] = str(project_root / "renders" / "slideshow_timeline.json")
    project["render"]["edit_decision_list_path"] = str(project_root / "renders" / "edit_decision_list.json")
    project["render"]["render_report_json_path"] = str(project_root / "logs" / "render_report.json")
    project["render"]["final_video_path"] = str(project_root / "renders" / "final_video.mp4")
    project["logs"]["render_report_path"] = str(project_root / "logs" / "render_report.md")
    project["logs"]["final_qa_report_path"] = str(project_root / "logs" / "final_qa_report.md")

    scenes = [
        {
            "scene_id": "scene_0001",
            "frame_id": "F0001",
            "beat_id": "beat_0001",
            "visual_slot_id": "VS0001",
            "shot_index": 1,
            "start": 0.0,
            "end": 4.0,
            "duration": 4.0,
            "voice_text": "Pink Panther investigators map the first route.",
            "visualized_claim": "pink route board establishes the opening route",
            "must_show": ["pink route board", "camera marker wall"],
            "prompt": "pink route board, camera marker wall, grounded evidence room",
            "final_prompt": "pink route board, camera marker wall, grounded evidence room",
            "why_this_frame_exists": "Show the opening route clearly.",
            "generation_decision": "new_image",
            "slot_type": "establishing_shot",
            "film_block_id": "pink_panther_room",
            "key_beat": False,
            "variant_count": 1,
        },
        {
            "scene_id": "scene_0002",
            "frame_id": "F0002",
            "beat_id": "beat_0002",
            "visual_slot_id": "VS0002",
            "shot_index": 2,
            "start": 4.0,
            "end": 8.0,
            "duration": 4.0,
            "voice_text": "The same board holds while the narrator lingers on the clue.",
            "visualized_claim": "the first clue stays on screen for emphasis",
            "must_show": ["same pink route board"],
            "prompt": "same pink route board held for emphasis",
            "final_prompt": "same pink route board held for emphasis",
            "why_this_frame_exists": "Hold the previous image for continuity.",
            "generation_decision": "hold_previous",
            "slot_type": "continuation_motion",
            "film_block_id": "pink_panther_room",
            "key_beat": False,
            "variant_count": 0,
        },
        {
            "scene_id": "scene_0003",
            "frame_id": "F0003",
            "beat_id": "beat_0003",
            "visual_slot_id": "VS0003",
            "shot_index": 3,
            "start": 8.0,
            "end": 12.0,
            "duration": 4.0,
            "voice_text": "Motion continues across the same setup.",
            "visualized_claim": "the same setup continues into the next beat",
            "must_show": ["same evidence board and pink route"],
            "prompt": "same evidence board and pink route, gentle continuation",
            "final_prompt": "same evidence board and pink route, gentle continuation",
            "why_this_frame_exists": "Continue the same setup without a new generation.",
            "generation_decision": "continuation_motion",
            "slot_type": "continuation_motion",
            "film_block_id": "pink_panther_room",
            "key_beat": False,
            "variant_count": 0,
        },
        {
            "scene_id": "scene_0004",
            "frame_id": "F0004",
            "beat_id": "beat_0004",
            "visual_slot_id": "VS0004",
            "shot_index": 4,
            "start": 12.0,
            "end": 16.0,
            "duration": 4.0,
            "voice_text": "A new detail insert shows the second clue.",
            "visualized_claim": "receipt detail proves the second clue",
            "must_show": ["pink receipt tray", "timestamp card"],
            "prompt": "pink receipt tray, timestamp card, grounded documentary detail insert",
            "final_prompt": "pink receipt tray, timestamp card, grounded documentary detail insert",
            "why_this_frame_exists": "Show the second clue as a new generated frame.",
            "generation_decision": "new_image",
            "slot_type": "detail_insert",
            "film_block_id": "pink_panther_room",
            "key_beat": False,
            "variant_count": 1,
        },
    ]

    prompt_text = "\n\n".join(
        [
            "No character reference. pink route board, camera marker wall, grounded evidence room",
            "No character reference. pink receipt tray, timestamp card, grounded documentary detail insert",
        ]
    ) + "\n"
    prompt_file = project_root / "exports" / "fastgen_prompts.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    package_items = [
        {"scene_id": "scene_0001", "frame_id": "F0001", "visual_slot_id": "VS0001", "variant_count": 1, "beat_id": "beat_0001"},
        {"scene_id": "scene_0004", "frame_id": "F0004", "visual_slot_id": "VS0004", "variant_count": 1, "beat_id": "beat_0004"},
    ]
    package_signature = stable_hash({"eligible_frames": ["F0001", "F0004"], "items": package_items})
    meta_payload = {
        "package_path": str(project_root / "prompts" / "generation_locked_frames.json"),
        "package_signature": package_signature,
        "prompt_count": 2,
        "non_generative_frame_count": 2,
        "package_items": package_items,
    }
    meta_payload["export_signature"] = stable_hash(
        {
            "package_path": meta_payload["package_path"],
            "package_signature": meta_payload["package_signature"],
            "prompt_count": meta_payload["prompt_count"],
            "content": prompt_text,
        }
    )
    write_json(prompt_file.with_suffix(prompt_file.suffix + ".meta.json"), meta_payload)
    write_json(prompt_file.with_suffix(".batches.json"), {"batches": [{"batch_id": "batch_0001", "prompt_indices": [1, 2]}]})
    write_json(project_root / "prompts" / "prompt_package.json", {"items": scenes})
    write_json(project_root / "scene_plan" / "final_scene_plan.json", {"scenes": scenes})
    write_json(project_root / "scene_plan" / "scene_plan.json", {"scenes": scenes})
    write_json(project_root / "prompts" / "fastgen_ref_paths.json", {})
    write_json(project_root / "planning" / "narration_beats.json", {"beats": scenes})
    write_json(
        project_root / "planning" / "visual_allocation_plan.json",
        {
            "metrics": {
                "narration_beats_count": 4,
                "visual_slots_count": 4,
                "new_image_slots_count": 2,
                "hold_or_continuation_slots_count": 2,
                "average_slot_duration": 4.0,
            },
            "visual_slots": [
                {"visual_slot_id": "VS0001", "beat_ids": ["beat_0001"], "scene_ids": ["scene_0001"], "generation_decision": "new_image", "slot_type": "establishing_shot"},
                {"visual_slot_id": "VS0002", "beat_ids": ["beat_0002"], "scene_ids": ["scene_0002"], "generation_decision": "hold_previous", "slot_type": "continuation_motion"},
                {"visual_slot_id": "VS0003", "beat_ids": ["beat_0003"], "scene_ids": ["scene_0003"], "generation_decision": "continuation_motion", "slot_type": "continuation_motion"},
                {"visual_slot_id": "VS0004", "beat_ids": ["beat_0004"], "scene_ids": ["scene_0004"], "generation_decision": "new_image", "slot_type": "detail_insert"},
            ],
        },
    )
    write_json(project_root / "reports" / "visual_calibration_report.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(project_root / "reports" / "visual_calibration_report.md", {"status": "pass"})
    write_json(project_root / "exports" / "montage_timing_map.json", [])
    write_json(project_root / "qc" / "continuity_qc_report.json", {"status": "pass", "warnings": [], "errors": []})
    write_json(project_root / "qc" / "regeneration_plan.json", {"tasks": []})
    write_json(project_root / "qc" / "review_decisions.json", {"decisions": []})
    write_json(project_root / "logs" / "render_report.json", {"status": "pending"})

    project_json = project_root / "project.json"
    write_json(project_json, project)
    return project_json


def mark_successful_frame(project_json: Path, *, frame_id: str, scene_id: str, visual_slot_id: str, prompt: str) -> Path:
    project = json.loads(project_json.read_text(encoding="utf-8"))
    state_db = resolve_state_db_path(project_json, project)
    image_path = Path(project["images"]["raw_images_dir"]) / f"{scene_id}_V01.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(TINY_PNG)
    prompt_settings = {"provider": "fastgen_openai_v4", "size": "1024x1024", "aspect_ratio": "16:9"}
    conn = connect_state_db(state_db)
    try:
        mark_frame_success(
            conn,
            project_id=project["project_id"],
            frame_id=frame_id,
            visual_slot_id=visual_slot_id,
            prompt_hash=compute_prompt_hash(prompt=prompt, refs=[], settings=prompt_settings),
            image_path=str(image_path),
        )
    finally:
        conn.close()
    return image_path


def mark_failed_frame(project_json: Path, *, frame_id: str, visual_slot_id: str) -> None:
    project = json.loads(project_json.read_text(encoding="utf-8"))
    state_db = resolve_state_db_path(project_json, project)
    conn = connect_state_db(state_db)
    try:
        mark_frame_failed(
            conn,
            project_id=project["project_id"],
            frame_id=frame_id,
            visual_slot_id=visual_slot_id,
            prompt_hash="failed-hash",
            error_message="synthetic failure",
        )
    finally:
        conn.close()


def test_real_generation_flag_required_for_pending_frames():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_project_fastgen_generation.py"),
                "--project-json",
                str(project_json),
                "--profile",
                "technical_fastgen_pilot",
                "--limit-frames",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        assert result.returncode != 0
        assert "--real-generation" in (result.stderr or result.stdout)


def test_limit_frames_only_counts_generative_slots():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        project = json.loads(project_json.read_text(encoding="utf-8"))
        selection = select_generation_items(
            state_db_path=resolve_state_db_path(project_json, project),
            project_id=project["project_id"],
            prompt_file=Path(project["prompts"]["fastgen_export_path"]),
            workdir=Path(project["images"]["run_manifest_path"]).parent,
            limit_frames=1,
            retry_failed_only=False,
            requested_frame_ids=[],
        )
        assert selection["selected_source_indices"] == [1]
        assert selection["selected_frame_ids"] == ["F0001"]
        assert selection["planned_generative_frames_count"] == 2
        assert selection["skipped_due_to_limit_count"] == 1


def test_hold_previous_and_continuation_do_not_count_toward_limit():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        project = json.loads(project_json.read_text(encoding="utf-8"))
        selection = select_generation_items(
            state_db_path=resolve_state_db_path(project_json, project),
            project_id=project["project_id"],
            prompt_file=Path(project["prompts"]["fastgen_export_path"]),
            workdir=Path(project["images"]["run_manifest_path"]).parent,
            limit_frames=1,
            retry_failed_only=False,
            requested_frame_ids=[],
        )
        assert selection["non_generative_slots_count"] == 2
        assert selection["planned_generative_frames_count"] == 2


def test_resume_skips_successful_frames():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        project = json.loads(project_json.read_text(encoding="utf-8"))
        mark_successful_frame(
            project_json,
            frame_id="F0001",
            scene_id="scene_0001",
            visual_slot_id="VS0001",
            prompt="pink route board, camera marker wall, grounded evidence room",
        )
        selection = select_generation_items(
            state_db_path=resolve_state_db_path(project_json, project),
            project_id=project["project_id"],
            prompt_file=Path(project["prompts"]["fastgen_export_path"]),
            workdir=Path(project["images"]["run_manifest_path"]).parent,
            limit_frames=15,
            retry_failed_only=False,
            requested_frame_ids=[],
        )
        assert selection["skipped_existing_success_count"] == 1
        assert selection["selected_source_indices"] == [2]
        assert selection["selected_frame_ids"] == ["F0004"]


def test_retry_failed_only_targets_failed_frames():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        project = json.loads(project_json.read_text(encoding="utf-8"))
        mark_successful_frame(
            project_json,
            frame_id="F0001",
            scene_id="scene_0001",
            visual_slot_id="VS0001",
            prompt="pink route board, camera marker wall, grounded evidence room",
        )
        mark_failed_frame(project_json, frame_id="F0004", visual_slot_id="VS0004")
        selection = select_generation_items(
            state_db_path=resolve_state_db_path(project_json, project),
            project_id=project["project_id"],
            prompt_file=Path(project["prompts"]["fastgen_export_path"]),
            workdir=Path(project["images"]["run_manifest_path"]).parent,
            limit_frames=15,
            retry_failed_only=True,
            requested_frame_ids=[],
        )
        assert selection["selected_source_indices"] == [2]
        assert selection["selected_frame_ids"] == ["F0004"]
        assert selection["skipped_existing_success_count"] == 1


def test_manifest_records_limited_pilot_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        mark_successful_frame(
            project_json,
            frame_id="F0001",
            scene_id="scene_0001",
            visual_slot_id="VS0001",
            prompt="pink route board, camera marker wall, grounded evidence room",
        )
        mark_successful_frame(
            project_json,
            frame_id="F0004",
            scene_id="scene_0004",
            visual_slot_id="VS0004",
            prompt="pink receipt tray, timestamp card, grounded documentary detail insert",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_project_fastgen_generation.py"),
                "--project-json",
                str(project_json),
                "--profile",
                "technical_fastgen_pilot",
                "--limit-frames",
                "1",
                "--resume",
                "--real-generation",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        manifest = json.loads((project_json.parent / "images" / "run" / "run_manifest.json").read_text(encoding="utf-8"))
        assert manifest["limited_pilot"] is True
        assert manifest["real_generation"] is True
        assert manifest["profile"] == "technical_fastgen_pilot"
        assert manifest["limit_frames"] == 1
        assert manifest["generated_count"] == 2
        assert manifest["skipped_existing_success_count"] == 2
        assert manifest["non_generative_slots_count"] == 2
        assert manifest["provider"] == "fastgen_openai_v4"
        assert manifest["started_at"]
        assert manifest["finished_at"]


def test_preflight_fails_clearly_if_credentials_missing(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        project = json.loads(project_json.read_text(encoding="utf-8"))
        monkeypatch.delenv("FAST_GEN_API_KEY", raising=False)
        monkeypatch.setattr(preflight_module, "ENV_PATH", Path(tmp) / "missing.env")
        try:
            preflight_module.run_real_generation_preflight(
                project_json=project_json,
                project=project,
                profile=None,
                real_generation=True,
                limit_frames=15,
            )
        except RuntimeError as exc:
            assert "FAST_GEN_API_KEY" in str(exc)
        else:
            raise AssertionError("Expected missing FastGen credentials to fail preflight")


def test_preflight_fails_if_visual_calibration_report_missing(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        project = json.loads(project_json.read_text(encoding="utf-8"))
        Path(project["reports"]["visual_calibration_report_json_path"]).unlink()
        monkeypatch.setenv("FAST_GEN_API_KEY", "test-key")
        monkeypatch.setattr(preflight_module, "ENV_PATH", Path(tmp) / "missing.env")
        try:
            preflight_module.run_real_generation_preflight(
                project_json=project_json,
                project=project,
                profile=None,
                real_generation=True,
                limit_frames=15,
            )
        except FileNotFoundError as exc:
            assert "visual_calibration_report" in str(exc)
        else:
            raise AssertionError("Expected missing calibration report to fail preflight")


def test_downstream_production_report_marks_partial_pilot():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        project_root = project_json.parent
        image_path = mark_successful_frame(
            project_json,
            frame_id="F0001",
            scene_id="scene_0001",
            visual_slot_id="VS0001",
            prompt="pink route board, camera marker wall, grounded evidence room",
        )
        write_json(
            project_root / "images" / "run" / "run_manifest.json",
            {
                "limited_pilot": True,
                "partial_pilot": True,
                "real_generation": True,
                "profile": "technical_fastgen_pilot",
                "limit_frames": 1,
                "generated_count": 1,
                "completed_count": 1,
                "failed_count": 0,
                "missing_count": 0,
                "planned_generative_frames_count": 2,
                "skipped_existing_success_count": 0,
                "skipped_due_to_limit_count": 1,
                "non_generative_slots_count": 2,
                "provider": "fastgen_openai_v4",
                "generated_images": [
                    {
                        "scene_id": "scene_0001",
                        "frame_id": "F0001",
                        "visual_slot_id": "VS0001",
                        "variant_index": 1,
                        "variant_label": "V01",
                        "variant_count": 1,
                        "status": "success",
                        "image_path": str(image_path),
                        "prompt": "pink route board, camera marker wall, grounded evidence room",
                    }
                ],
            },
        )
        project = json.loads(project_json.read_text(encoding="utf-8"))
        project["images"]["status"] = "pilot_partial"
        write_json(project_json, project)
        write_json(
            project_root / "qc" / "image_qc_report.json",
            {
                "images": [
                    {
                        "scene_id": "scene_0001",
                        "beat_id": "beat_0001",
                        "decision": "use",
                        "coverage_status": "pass",
                        "technical_qc_passed": True,
                        "file_path": str(image_path),
                    }
                ]
            },
        )
        write_json(
            project_root / "qc" / "selected_images_manifest.json",
            {
                "selected_images": [
                    {
                        "scene_id": "scene_0001",
                        "frame_id": "F0001",
                        "beat_id": "beat_0001",
                        "selection_status": "use",
                        "coverage_status": "pass",
                        "selected_image_path": str(image_path),
                        "normalized_image_path": str(image_path),
                        "voice_text": "Pink Panther investigators map the first route.",
                        "visualized_claim": "pink route board establishes the opening route",
                    }
                ]
            },
        )

        for script_name, extra_args in [
            ("build_project_slideshow_timeline.py", []),
            ("render_project_slideshow_video.py", ["--dry-run"]),
            ("build_production_report.py", []),
        ]:
            subprocess.run(
                [sys.executable, str(SCRIPTS / script_name), "--project-json", str(project_json), *extra_args],
                check=True,
                timeout=30,
                env=cli_env(),
            )

        report = json.loads((project_root / "reports" / "production_report.json").read_text(encoding="utf-8"))
        assert report["status"] == "pilot_partial"
        assert report["metrics"]["partial_pilot"] is True
        assert report["metrics"]["pilot_limit_frames"] == 1
        assert report["metrics"]["pilot_skipped_due_to_limit_count"] == 1
        dashboard_env = cli_env()
        status_result = subprocess.run(
            [sys.executable, "-m", "yt_nonstop.cli", "status", "--project-json", str(project_json)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=dashboard_env,
        )
        assert "partial pilot" in status_result.stdout.lower()


def test_legacy_wrapper_flags_still_parse():
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_pilot_fixture(Path(tmp))
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_fastgen_only_project.py"),
                "--project-json",
                str(project_json),
                "--from",
                "generate_images",
                "--to",
                "generate_images",
                "--dry-run",
                "--profile",
                "technical_fastgen_pilot",
                "--limit-frames",
                "1",
                "--real-generation",
                "--render-dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=cli_env(),
        )
        assert "DRY-RUN:" in result.stdout
        assert "--limit-frames 1" in result.stdout
        assert "--real-generation" in result.stdout


def test_full_creative_pilot_enables_llm_runtime_defaults():
    project = {"project_id": "pilot", "workflow": {}, "runtime": {}, "qc": {}}
    args = argparse.Namespace(
        profile="full_creative_pilot",
        auto_author_llm=False,
        image_retry_rounds=3,
        render_dry_run=False,
        limit_frames=0,
        real_generation=False,
    )
    profile = apply_runtime_profile(project, args)
    assert profile is not None
    assert profile.name == "full_creative_pilot"
    assert args.auto_author_llm is True
    assert args.render_dry_run is True
    assert args.image_retry_rounds == 1
    assert effective_limit_frames(project, args.limit_frames, profile) == 15
