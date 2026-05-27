import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from generation_lock import lock_record  # noqa: E402
from pipeline_contracts import prompt_has_text_conflict, prompt_restates_srt, stable_hash  # noqa: E402
from validate_project import validate_export_generation_batches, validate_quality_assurance  # noqa: E402


class FastGenContractTests(unittest.TestCase):
    def test_generation_lock_rejects_direct_srt_and_text_conflict(self):
        frame_brief = {
            "frame_id": "F0001",
            "srt_text": "This exact narration sentence should not be copied into the prompt.",
            "continuity_tags": ["evidence_table"],
            "frame_brief_hash": stable_hash({"frame_id": "F0001"}),
            "prompt_contract_version": "v1",
            "llm_model_id": "codex-gpt-5",
            "llm_prompt_template_version": "fastgen-frame-brief-v1",
            "generation_lock_version": "lock-v1",
            "motion_treatment": "slow_push_in",
            "camera_storyboard": "top-down evidence layout",
            "screen_action": "documents imply the hidden mechanism",
        }
        scene = {
            "final_prompt": "This exact narration sentence should not be copied into the prompt. Also show readable text, but no readable text.",
            "negative_prompt": "logos, subtitles",
            "continuity_notes": "Keep the evidence table consistent.",
        }
        locked, errors, _warnings = lock_record(frame_brief, scene, "")
        self.assertEqual(locked["generation_lock_status"], "failed")
        self.assertIn("direct_srt_in_prompt", errors)
        self.assertIn("text_conflict", errors)

    def test_prompt_text_conflict_helper(self):
        self.assertTrue(prompt_has_text_conflict("Show readable text on a label but no readable text anywhere else"))
        self.assertTrue(prompt_restates_srt("The frame says hidden mechanism revealed at dusk", "hidden mechanism revealed at dusk"))
        self.assertFalse(prompt_has_text_conflict("No text, no subtitles, no readable text, no labels"))

    def test_quality_assurance_flags_adjacent_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame_briefs_path = root / "frame_briefs.json"
            locked_path = root / "generation_locked_frames.json"
            report_path = root / "qa_report.json"
            project = {
                "project_id": "contract_test",
                "workflow": {"strict_generation_lock": False, "task_type": "full_build", "is_sequence": True, "skip_storyboard_allowed": False, "requested_format": "json"},
                "planning": {"frame_briefs_json_path": str(frame_briefs_path)},
                "prompts": {"generation_locked_json_path": str(locked_path)},
                "logs": {"qa_report_json_path": str(report_path)},
            }
            frame_briefs = [
                {
                    "frame_id": "F0001",
                    "scene_id": "scene_0001",
                    "timeline_in": 0.0,
                    "timeline_out": 1.0,
                    "scale": "wide",
                    "angle": "eye-level",
                    "scene_type": "place",
                    "lighting": "cold",
                    "emotional_energy": "steady",
                    "visual_density": "clean",
                    "motion_treatment": "static_tension",
                },
                {
                    "frame_id": "F0002",
                    "scene_id": "scene_0002",
                    "timeline_in": 1.0,
                    "timeline_out": 2.0,
                    "scale": "wide",
                    "angle": "eye-level",
                    "scene_type": "place",
                    "lighting": "cold",
                    "emotional_energy": "steady",
                    "visual_density": "clean",
                    "motion_treatment": "static_tension",
                },
            ]
            locked_rows = [
                {"frame_id": "F0001", "generation_lock_status": "locked", "image_prompt": "prompt one"},
                {"frame_id": "F0002", "generation_lock_status": "locked", "image_prompt": "prompt two"},
            ]
            frame_briefs_path.write_text(json.dumps(frame_briefs), encoding="utf-8")
            locked_path.write_text(json.dumps(locked_rows), encoding="utf-8")
            errors, warnings = validate_quality_assurance(project)
            self.assertTrue(any("neighbor_duplicate" in item for item in errors))

    def test_build_frame_briefs_requires_storyboard_for_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scene_plan_path = root / "scene_plan.json"
            frame_briefs_path = root / "frame_briefs.json"
            frame_briefs_csv_path = root / "frame_briefs.csv"
            prompt_package_path = root / "prompt_package.json"
            project_json = root / "project.json"
            scene_plan_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene_0001",
                                "source_segment_id": 1,
                                "start": 0.0,
                                "end": 1.0,
                                "duration": 1.0,
                                "voice_text": "hello",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "brief_gate_test",
                        "profile_id": "fastgen_only",
                        "schema_version": "draft-1",
                        "meta": {"project_root": str(root)},
                        "workflow": {"task_type": "full_build", "is_sequence": True, "skip_storyboard_allowed": False},
                        "scene_plan": {"scene_plan_path": str(scene_plan_path)},
                        "planning": {
                            "storyboard_path": str(root / "missing_storyboard.json"),
                            "frame_briefs_json_path": str(frame_briefs_path),
                            "frame_briefs_csv_path": str(frame_briefs_csv_path),
                            "continuity_map_json_path": str(root / "continuity_entities.json"),
                            "continuity_bible_md_path": str(root / "continuity_bible.md"),
                            "scene_map_path": str(root / "scene_map.json"),
                            "sentence_blocks_json_path": str(root / "sentence_blocks.json"),
                            "sentence_blocks_txt_path": str(root / "sentence_blocks.txt"),
                        },
                        "prompts": {
                            "prompt_package_path": str(prompt_package_path),
                            "prompt_language": "English",
                            "style_preset": "cinematic-realistic-v1",
                            "global_style_summary": None,
                            "authoring_model": "codex-gpt-5",
                        },
                        "logs": {
                            "pipeline_log_path": str(root / "pipeline.log"),
                            "events_jsonl_path": str(root / "events.jsonl"),
                            "input_validation_report_path": str(root / "input_validation_report.md"),
                            "timing_cleanup_report_path": str(root / "timing_cleanup_report.md"),
                            "scene_qa_report_path": str(root / "scene_qa_report.md"),
                            "scene_qa_json_path": str(root / "scene_qa.json"),
                            "narrative_editor_report_path": str(root / "narrative_editor_report.md"),
                            "visual_direction_report_path": str(root / "visual_direction_report.md"),
                            "brand_realism_report_path": str(root / "brand_realism_report.md"),
                            "prompt_qa_report_path": str(root / "prompt_qa_report.md"),
                            "prompt_qa_json_path": str(root / "prompt_qa.json"),
                            "generation_lock_report_path": str(root / "generation_lock_report.md"),
                            "qa_report_json_path": str(root / "qa_report.json"),
                            "workflow_report_path": str(root / "workflow_report.md"),
                            "workflow_report_json_path": str(root / "workflow_report.json"),
                            "export_report_path": str(root / "export_report.md"),
                            "generation_report_path": str(root / "generation_report.md"),
                            "render_report_path": str(root / "render_report.md"),
                            "final_review_report_path": str(root / "final_review_report.md"),
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "build_frame_briefs.py"), "--project-json", str(project_json)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires storyboard output", result.stderr or result.stdout)

    def test_continuity_map_feeds_context_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scene_plan_path = root / "scene_plan.json"
            prompt_package_path = root / "prompt_package.json"
            continuity_path = root / "continuity_entities.json"
            context_pack_path = root / "scene_context_pack.json"
            raw_text_path = root / "raw_text.md"
            project_json = root / "project.json"
            raw_text_path.write_text("A boutique robbery story.", encoding="utf-8")
            scene_plan_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene_0001",
                                "shot_index": 1,
                                "source_segment_id": 1,
                                "start": 0.0,
                                "end": 1.5,
                                "duration": 1.5,
                                "voice_text": "The two operators enter the boutique.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            prompt_package_path.write_text(
                json.dumps({"items": [{"scene_id": "scene_0001", "reference_ids": ["ref-001"]}]}),
                encoding="utf-8",
            )
            continuity_path.write_text(
                json.dumps(
                    {
                        "continuity_world": "Same boutique world.",
                        "continuity_rules": ["Keep recurring people identical."],
                        "recurring_motifs": ["glass reflections"],
                        "character_profiles": [{"entity_id": "lead_operator", "profile": "same lead operator profile"}],
                        "object_profiles": [],
                        "location_profiles": [],
                        "segment_entity_map": {"1": {"active_entities": ["lead_operator"], "continuity_focus": "same lead operator"}},
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "context_pack_test",
                        "meta": {"project_root": str(root), "language": "en"},
                        "workflow": {"is_sequence": True},
                        "rewrite": {"source_text_path": str(raw_text_path)},
                        "inputs": {"raw_text_path": str(raw_text_path)},
                        "scene_plan": {"scene_plan_path": str(scene_plan_path)},
                        "planning": {"continuity_map_json_path": str(continuity_path)},
                        "prompts": {
                            "prompt_language": "English",
                            "prompt_package_path": str(prompt_package_path),
                            "scene_context_pack_path": str(context_pack_path),
                            "style_guide_path": str(root / "style_guide.json"),
                        },
                        "logs": {
                            "pipeline_log_path": str(root / "pipeline.log"),
                            "events_jsonl_path": str(root / "events.jsonl"),
                            "input_validation_report_path": str(root / "input_validation_report.md"),
                            "timing_cleanup_report_path": str(root / "timing_cleanup_report.md"),
                            "scene_qa_report_path": str(root / "scene_qa_report.md"),
                            "scene_qa_json_path": str(root / "scene_qa.json"),
                            "narrative_editor_report_path": str(root / "narrative_editor_report.md"),
                            "visual_direction_report_path": str(root / "visual_direction_report.md"),
                            "brand_realism_report_path": str(root / "brand_realism_report.md"),
                            "prompt_qa_report_path": str(root / "prompt_qa_report.md"),
                            "prompt_qa_json_path": str(root / "prompt_qa.json"),
                            "generation_lock_report_path": str(root / "generation_lock_report.md"),
                            "qa_report_json_path": str(root / "qa_report.json"),
                            "workflow_report_path": str(root / "workflow_report.md"),
                            "workflow_report_json_path": str(root / "workflow_report.json"),
                            "export_report_path": str(root / "export_report.md"),
                            "generation_report_path": str(root / "generation_report.md"),
                            "render_report_path": str(root / "render_report.md"),
                            "final_review_report_path": str(root / "final_review_report.md"),
                        },
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_scene_context_pack.py"), "--project-json", str(project_json)],
                check=True,
            )
            payload = json.loads(context_pack_path.read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["active_entity_ids"], ["lead_operator"])
            self.assertEqual(payload[0]["reference_ids"], ["ref-001"])
            self.assertEqual(payload[0]["continuity_mode"], "profiled")

    def test_export_batch_count_respects_allowed_locked_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_path = root / "fastgen_prompts.md"
            locked_path = root / "generation_locked_frames.json"
            project = {
                "workflow": {"strict_generation_lock": False},
                "prompts": {
                    "fastgen_export_path": str(export_path),
                    "generation_locked_json_path": str(locked_path),
                },
            }
            locked_rows = [
                {"frame_id": "F0001", "generation_lock_status": "locked"},
                {"frame_id": "F0002", "generation_lock_status": "locked_with_warnings"},
                {"frame_id": "F0003", "generation_lock_status": "failed"},
            ]
            locked_path.write_text(json.dumps(locked_rows), encoding="utf-8")
            export_path.write_text("block-one\n\nblock-two\n", encoding="utf-8")
            errors, _warnings = validate_export_generation_batches(project)
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
