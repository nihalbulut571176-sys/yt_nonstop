import base64
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
from llm_pipeline_contracts import classify_generation_error, validate_generation_manifest  # noqa: E402
from pipeline_contracts import prompt_has_text_conflict, prompt_restates_srt, stable_hash  # noqa: E402
from validate_project import validate_author_narration_beats, validate_build_reference_prompt_pack, validate_export_generation_batches, validate_image_qc, validate_quality_assurance  # noqa: E402
from attach_reference_assets import resolve_reference_bindings  # noqa: E402
from yt_nonstop.utils.text_repair import repair_mojibake_text  # noqa: E402


class FastGenContractTests(unittest.TestCase):
    @staticmethod
    def write_tiny_png(path: Path) -> None:
        path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9uoAAAAASUVORK5CYII="))

    def test_generation_lock_rejects_direct_srt_and_text_conflict(self):
        frame_brief = {
            "frame_id": "F0001",
            "beat_id": "beat_0001",
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

    def test_repair_mojibake_text_restores_russian(self):
        broken = "РџСЂРµРґСЃС‚Р°РІСЊС‚Рµ СЃРµР±Рµ СЋРІРµР»РёСЂРЅС‹Р№ Р±СѓС‚РёРє."
        self.assertEqual(repair_mojibake_text(broken), "Представьте себе ювелирный бутик.")

    def test_reference_routing_skips_optional_character_refs_for_non_human_shot(self):
        frame = {
            "shot_role": "aftermath_escape",
            "slot_type": "explanation_visual",
            "shot_type": "wide exit-facing angle",
            "subject_visible": False,
            "visible_subject_ids": [],
            "primary_subject_id": "boutique_attendant",
            "entity_locks": [],
        }
        subject_map = {
            "boutique_attendant": {
                "subject_id": "boutique_attendant",
                "subject_type": "character",
                "reference_policy": "optional",
                "reference_asset_ids": ["ref_attendant"],
            }
        }
        asset_map = {"ref_attendant": {"path": __file__}}
        bindings, flags = resolve_reference_bindings(frame, subject_map, asset_map)
        self.assertEqual(bindings, [])
        self.assertEqual(flags, [])

    def test_reference_routing_keeps_required_character_refs_for_human_shot(self):
        frame = {
            "shot_role": "operator_entry",
            "slot_type": "explanation_visual",
            "shot_type": "medium documentary angle",
            "subject_visible": True,
            "visible_subject_ids": ["lead_operator"],
            "primary_subject_id": "lead_operator",
            "entity_locks": [{"entity_id": "lead_operator", "reference_policy": "required"}],
        }
        subject_map = {
            "lead_operator": {
                "subject_id": "lead_operator",
                "subject_type": "character",
                "reference_policy": "required",
                "reference_asset_ids": ["ref_lead"],
            }
        }
        asset_map = {"ref_lead": {"path": __file__}}
        bindings, flags = resolve_reference_bindings(frame, subject_map, asset_map)
        self.assertEqual([binding["subject_id"] for binding in bindings], ["lead_operator"])
        self.assertEqual(flags, [])

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
                    "beat_id": "beat_0001",
                    "scene_id": "scene_0001",
                    "timeline_in": 0.0,
                    "timeline_out": 1.0,
                    "visualized_claim": "cold evidence table establishes the setup",
                    "must_show": ["cold evidence table"],
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
                    "beat_id": "beat_0002",
                    "scene_id": "scene_0002",
                    "timeline_in": 1.0,
                    "timeline_out": 2.0,
                    "visualized_claim": "cold evidence table stays in view",
                    "must_show": ["cold evidence table"],
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
                {"frame_id": "F0001", "beat_id": "beat_0001", "generation_lock_status": "locked", "image_prompt": "cold evidence table prompt one"},
                {"frame_id": "F0002", "beat_id": "beat_0002", "generation_lock_status": "locked", "image_prompt": "cold evidence table prompt two"},
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

    def test_build_frame_briefs_requires_visual_shot_plan_for_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scene_plan_path = root / "scene_plan.json"
            storyboard_path = root / "storyboard.json"
            frame_briefs_path = root / "frame_briefs.json"
            frame_briefs_csv_path = root / "frame_briefs.csv"
            prompt_package_path = root / "prompt_package.json"
            narration_beats_path = root / "narration_beats.json"
            project_json = root / "project.json"
            scene_plan_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene_0001",
                                "source_segment_id": 1,
                                "shot_index": 1,
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
            storyboard_path.write_text(json.dumps({"items": [{"segment_id": 1}]}), encoding="utf-8")
            prompt_package_path.write_text(json.dumps({"items": [{"scene_id": "scene_0001"}]}), encoding="utf-8")
            narration_beats_path.write_text(
                json.dumps(
                    {
                        "beats": [
                            {
                                "beat_id": "beat_0001",
                                "scene_id": "scene_0001",
                                "start": 0.0,
                                "end": 1.0,
                                "duration": 1.0,
                                "voice_text": "hello",
                                "spoken_claim": "person enters room",
                                "must_visualize": ["person entering a room"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "brief_shot_plan_gate_test",
                        "profile_id": "fastgen_only",
                        "schema_version": "draft-1",
                        "meta": {"project_root": str(root)},
                        "workflow": {"task_type": "full_build", "is_sequence": True, "skip_storyboard_allowed": False},
                        "scene_plan": {"scene_plan_path": str(scene_plan_path)},
                        "planning": {
                            "storyboard_path": str(storyboard_path),
                            "frame_briefs_json_path": str(frame_briefs_path),
                            "frame_briefs_csv_path": str(frame_briefs_csv_path),
                            "continuity_map_json_path": str(root / "continuity_entities.json"),
                            "narration_beats_path": str(narration_beats_path),
                        },
                        "prompts": {
                            "prompt_package_path": str(prompt_package_path),
                            "visual_shot_plan_path": str(root / "missing_visual_shot_plan.json"),
                            "prompt_language": "English",
                            "style_preset": "cinematic-realistic-v1",
                            "global_style_summary": None,
                            "authoring_model": "codex-gpt-5",
                            "subject_registry_path": str(root / "subject_registry.json"),
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
            self.assertIn("requires visual_shot_plan output", result.stderr or result.stdout)

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
                {"frame_id": "F0001", "beat_id": "beat_0001", "generation_lock_status": "locked"},
                {"frame_id": "F0002", "beat_id": "beat_0002", "generation_lock_status": "locked_with_warnings"},
                {"frame_id": "F0003", "beat_id": "beat_0003", "generation_lock_status": "failed"},
            ]
            locked_path.write_text(json.dumps(locked_rows), encoding="utf-8")
            export_path.write_text("block-one\n\nblock-two\n", encoding="utf-8")
            errors, _warnings = validate_export_generation_batches(project)
            self.assertEqual(errors, [])

    def test_generation_lock_carries_reference_binding_fields(self):
        frame_brief = {
            "frame_id": "F0002",
            "beat_id": "beat_0002",
            "srt_text": "A security guard watches the boutique entrance.",
            "continuity_tags": ["security_guard_01"],
            "frame_brief_hash": stable_hash({"frame_id": "F0002"}),
            "prompt_contract_version": "v1",
            "llm_model_id": "codex-gpt-5",
            "llm_prompt_template_version": "fastgen-frame-brief-v1",
            "generation_lock_version": "lock-v1",
            "motion_treatment": "slow_push_in",
            "camera_storyboard": "entrance coverage",
            "screen_action": "guard visible near the door",
            "reference_bindings": [
                {
                    "subject_id": "security_guard_01",
                    "reference_asset_ids": ["ref_guard_front"],
                    "usage": "identity_and_wardrobe",
                    "strength": "strict",
                }
            ],
            "subject_continuity_strength": "strict",
        }
        scene = {
            "final_prompt": "Premium documentary still of a boutique guard near the entrance.",
            "negative_prompt": "logos, text",
            "continuity_notes": "Keep the same guard profile.",
            "reference_images": ["C:/refs/security_guard_01/front.jpg"],
        }
        locked, errors, warnings = lock_record(frame_brief, scene, "")
        self.assertEqual(errors, [])
        self.assertIn("too_generic", warnings)
        self.assertEqual(locked["reference_ids"], ["ref_guard_front"])
        self.assertEqual(locked["reference_images"], ["C:/refs/security_guard_01/front.jpg"])
        self.assertEqual(locked["reference_strength"], "strict")
        self.assertEqual(locked["reference_usage"], "identity_and_wardrobe")

    def test_generation_error_classifier_keeps_runtime_failures_technical(self):
        self.assertEqual(classify_generation_error("Operation polling timed out: op_123"), "timeout")
        self.assertEqual(classify_generation_error("File not found for ref_guard_front"), "filesystem_error")
        self.assertEqual(classify_generation_error("May violate our content policies"), "policy_violation")

    def test_validate_generation_manifest_rejects_success_without_real_file(self):
        manifest = {
            "job_id": "job-123",
            "generated_images": [
                {
                    "job_id": "job-123",
                    "scene_id": "scene_0001",
                    "source_prompt_index": 1,
                    "prompt_hash": "abc",
                    "generator_profile": "fastgen",
                    "created_at": "2026-05-28T00:00:00Z",
                    "status": "success",
                    "image_path": "C:/definitely/missing/file.png",
                }
            ],
            "failed_count": 0,
        }
        errors, _warnings = validate_generation_manifest(manifest)
        self.assertTrue(any("marked success but image file is missing" in item for item in errors))

    def test_validate_author_narration_beats_rejects_abstract_only_must_visualize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scene_plan_path = root / "scene_plan.json"
            beats_path = root / "narration_beats.json"
            scene_plan_path.write_text(
                json.dumps({"scenes": [{"scene_id": "scene_0001", "start": 0.0, "end": 1.0, "duration": 1.0, "voice_text": "hello"}]}),
                encoding="utf-8",
            )
            beats_path.write_text(
                json.dumps(
                    {
                        "beats": [
                            {
                                "beat_id": "beat_0001",
                                "scene_id": "scene_0001",
                                "start": 0.0,
                                "end": 1.0,
                                "duration": 1.0,
                                "voice_text": "hello",
                                "spoken_claim": "betrayal becomes visible",
                                "must_visualize": ["betrayal", "danger"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project = {"planning": {"narration_beats_path": str(beats_path)}, "scene_plan": {"scene_plan_path": str(scene_plan_path)}}
            errors, _warnings = validate_author_narration_beats(project)
            self.assertTrue(any("abstract-only must_visualize" in item for item in errors))

    def test_validate_image_qc_rejects_failed_selected_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qc_path = root / "image_qc_report.json"
            selected_path = root / "selected_images_manifest.json"
            image_path = root / "scene_0001.png"
            image_path.write_bytes(b"fake")
            qc_path.write_text(
                json.dumps({"images": [{"scene_id": "scene_0001"}]}),
                encoding="utf-8",
            )
            selected_path.write_text(
                json.dumps(
                    {
                        "selected_images": [
                            {
                                "scene_id": "scene_0001",
                                "beat_id": "beat_0001",
                                "voice_text": "voice",
                                "visualized_claim": "claim",
                                "selection_status": "reject",
                                "coverage_status": "fail",
                                "semantic_flags": ["missing"],
                                "selected_image_path": str(image_path),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project = {"images": {"image_qc_report_path": str(qc_path), "selected_images_manifest_path": str(selected_path)}}
            errors, _warnings = validate_image_qc(project)
            self.assertTrue(any("invalid selection_status" in item or "failed semantic coverage" in item for item in errors))

    def test_validate_image_qc_allows_manual_review_semantic_warnings_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qc_path = root / "image_qc_report.json"
            selected_path = root / "selected_images_manifest.json"
            image_path = root / "scene_0001.png"
            image_path.write_bytes(b"fake")
            qc_path.write_text(
                json.dumps({"images": [{"scene_id": "scene_0001"}]}),
                encoding="utf-8",
            )
            selected_path.write_text(
                json.dumps(
                    {
                        "selected_images": [
                            {
                                "scene_id": "scene_0001",
                                "beat_id": "beat_0001",
                                "voice_text": "voice",
                                "visualized_claim": "claim",
                                "selection_status": "manual_review",
                                "coverage_status": "fail",
                                "semantic_flags": ["must_show_not_grounded_in_prompt"],
                                "selected_image_path": str(image_path),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project = {
                "qc": {
                    "image_semantic_qc_mode": "disabled",
                    "allow_manual_review_without_vlm": True,
                },
                "images": {
                    "image_qc_report_path": str(qc_path),
                    "selected_images_manifest_path": str(selected_path),
                },
            }
            errors, warnings = validate_image_qc(project)
            self.assertEqual(errors, [])
            self.assertTrue(any("failed semantic coverage" in item for item in warnings))

    def test_qc_generated_images_accepts_enriched_manifest_without_success_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            (project_root / "prompts").mkdir(parents=True, exist_ok=True)
            (project_root / "images" / "run").mkdir(parents=True, exist_ok=True)
            image_path = project_root / "images" / "run" / "scene_0001_V01.png"
            self.write_tiny_png(image_path)
            prompt_package_path = project_root / "prompts" / "prompt_package.json"
            final_scene_plan_path = project_root / "prompts" / "final_scene_plan.json"
            narration_beats_path = project_root / "planning" / "narration_beats.json"
            run_manifest_path = project_root / "images" / "run" / "run_manifest.json"
            project_json = project_root / "project.json"
            narration_beats_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_package_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "scene_id": "scene_0001",
                                "voice_text": "voice",
                                "visualized_claim": "security guard near boutique entrance",
                                "must_show": ["security guard near boutique entrance"],
                                "reference_ids": [],
                                "entity_locks": [],
                                "shot_role": "security_system",
                                "prompt": "security guard near boutique entrance",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            final_scene_plan_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene_0001",
                                "frame_id": "F0001",
                                "beat_id": "beat_0001",
                                "voice_text": "voice",
                                "visualized_claim": "security guard near boutique entrance",
                                "must_show": ["security guard near boutique entrance"],
                                "reference_ids": [],
                                "entity_locks": [],
                                "shot_role": "security_system",
                                "prompt": "security guard near boutique entrance",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            narration_beats_path.write_text(
                json.dumps(
                    {
                        "beats": [
                            {
                                "beat_id": "beat_0001",
                                "scene_id": "scene_0001",
                                "voice_text": "voice",
                                "spoken_claim": "security guard near boutique entrance",
                                "must_visualize": ["security guard near boutique entrance"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            run_manifest_path.write_text(
                json.dumps(
                    {
                        "project_id": "qc_manifest_test",
                        "job_id": "job-1",
                        "generated_images": [
                            {
                                "scene_id": "scene_0001",
                                "variant_index": 1,
                                "variant_label": "V01",
                                "variant_count": 1,
                                "status": "success",
                                "image_path": str(image_path),
                                "normalized_image_path": str(image_path),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "qc_manifest_test",
                        "meta": {"project_root": str(project_root)},
                        "prompts": {
                            "prompt_package_path": str(prompt_package_path),
                            "final_scene_plan_path": str(final_scene_plan_path),
                        },
                        "planning": {"narration_beats_path": str(narration_beats_path)},
                        "images": {
                            "run_manifest_path": str(run_manifest_path),
                            "image_qc_report_path": str(project_root / "qc" / "image_qc_report.json"),
                            "selected_images_manifest_path": str(project_root / "qc" / "selected_images_manifest.json"),
                        },
                        "qc": {},
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "qc_generated_images.py"), "--project-json", str(project_json)],
                check=True,
            )
            qc_payload = json.loads((project_root / "qc" / "image_qc_report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(qc_payload["images"]), 1)

    def test_timeline_prefers_normalized_render_asset_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            (project_root / "exports").mkdir(parents=True, exist_ok=True)
            (project_root / "prompts").mkdir(parents=True, exist_ok=True)
            (project_root / "renders").mkdir(parents=True, exist_ok=True)
            raw_image = project_root / "raw.png"
            normalized_image = project_root / "normalized.png"
            raw_image.write_bytes(b"fake")
            normalized_image.write_bytes(b"fake")
            final_scene_plan_path = project_root / "prompts" / "final_scene_plan.json"
            montage_path = project_root / "exports" / "montage_timing_map.json"
            selected_path = project_root / "qc_selected.json"
            project_json = project_root / "project.json"
            final_scene_plan_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene_0001",
                                "frame_id": "F0001",
                                "shot_index": 1,
                                "start": 0.0,
                                "end": 1.0,
                                "voice_text": "voice",
                                "render_asset_path": str(normalized_image),
                                "still_image_path": str(normalized_image),
                                "visualized_claim": "claim",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            montage_path.write_text("[]", encoding="utf-8")
            selected_path.write_text(
                json.dumps(
                    {
                        "selected_images": [
                            {
                                "scene_id": "scene_0001",
                                "selection_status": "use",
                                "coverage_status": "pass",
                                "selected_image_path": str(raw_image),
                                "normalized_image_path": str(normalized_image),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "timeline_priority_test",
                        "meta": {"project_root": str(project_root)},
                        "inputs": {"audio_duration_seconds": 1.0},
                        "exports": {"montage_timing_map_json_path": str(montage_path)},
                        "prompts": {"final_scene_plan_path": str(final_scene_plan_path)},
                        "images": {"selected_images_manifest_path": str(selected_path)},
                        "render": {"edit_decision_list_path": str(project_root / "renders" / "edit_decision_list.json")},
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_project_slideshow_timeline.py"), "--project-json", str(project_json)],
                check=True,
            )
            timeline = json.loads((project_root / "renders" / "slideshow_timeline.json").read_text(encoding="utf-8"))
            self.assertEqual(timeline[0]["image"], str(normalized_image))

    def test_timeline_fails_on_rejected_selected_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            (project_root / "exports").mkdir(parents=True, exist_ok=True)
            (project_root / "prompts").mkdir(parents=True, exist_ok=True)
            raw_image = project_root / "raw.png"
            raw_image.write_bytes(b"fake")
            final_scene_plan_path = project_root / "prompts" / "final_scene_plan.json"
            montage_path = project_root / "exports" / "montage_timing_map.json"
            selected_path = project_root / "qc_selected.json"
            project_json = project_root / "project.json"
            final_scene_plan_path.write_text(
                json.dumps({"scenes": [{"scene_id": "scene_0001", "frame_id": "F0001", "shot_index": 1, "start": 0.0, "end": 1.0, "voice_text": "voice"}]}),
                encoding="utf-8",
            )
            montage_path.write_text("[]", encoding="utf-8")
            selected_path.write_text(
                json.dumps({"selected_images": [{"scene_id": "scene_0001", "selection_status": "reject", "selected_image_path": str(raw_image)}]}),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "timeline_reject_test",
                        "meta": {"project_root": str(project_root)},
                        "inputs": {"audio_duration_seconds": 1.0},
                        "exports": {"montage_timing_map_json_path": str(montage_path)},
                        "prompts": {"final_scene_plan_path": str(final_scene_plan_path)},
                        "images": {"selected_images_manifest_path": str(selected_path)},
                        "render": {"edit_decision_list_path": str(project_root / "renders" / "edit_decision_list.json")},
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "build_project_slideshow_timeline.py"), "--project-json", str(project_json)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not timeline-eligible", result.stderr or result.stdout)

    def test_attach_reference_assets_populates_visible_subject_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            (project_root / "planning").mkdir(parents=True, exist_ok=True)
            (project_root / "prompts").mkdir(parents=True, exist_ok=True)
            (project_root / "assets" / "references" / "characters" / "security_guard_01").mkdir(parents=True, exist_ok=True)
            (project_root / "assets" / "references" / "characters" / "security_guard_01" / "front.jpg").write_bytes(b"fake")
            frame_briefs_path = project_root / "planning" / "frame_briefs.json"
            scene_plan_path = project_root / "planning" / "scene_plan.json"
            subject_registry_path = project_root / "prompts" / "subject_registry.json"
            assets_manifest_path = project_root / "prompts" / "reference_assets.json"
            report_path = project_root / "planning" / "reference_binding_report.json"
            project_json = project_root / "project.json"
            frame_briefs_path.write_text(
                json.dumps(
                    [
                        {
                            "frame_id": "F0001",
                            "scene_id": "scene_0001",
                            "primary_subject_id": "security_guard_01",
                            "subject_visible": True,
                            "mentioned_subject_ids": ["security_guard_01"],
                            "visible_subject_ids": ["security_guard_01"],
                            "subject_continuity_strength": "strict",
                            "reference_bindings": [],
                        },
                        {
                            "frame_id": "F0002",
                            "scene_id": "scene_0002",
                            "primary_subject_id": "security_guard_01",
                            "subject_visible": False,
                            "mentioned_subject_ids": ["security_guard_01"],
                            "visible_subject_ids": [],
                            "subject_continuity_strength": "strict",
                            "reference_bindings": [],
                        },
                    ]
                ),
                encoding="utf-8",
            )
            scene_plan_path.write_text(
                json.dumps({"scenes": [{"scene_id": "scene_0001"}, {"scene_id": "scene_0002"}]}),
                encoding="utf-8",
            )
            subject_registry_path.write_text(
                json.dumps(
                    {
                        "subjects": [
                            {
                                "subject_id": "security_guard_01",
                                "reference_policy": "strict",
                                "reference_asset_ids": ["ref_security_guard_01_front"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            assets_manifest_path.write_text(
                json.dumps(
                    {
                        "reference_assets": [
                            {
                                "reference_asset_id": "ref_security_guard_01_front",
                                "subject_id": "security_guard_01",
                                "path": str(project_root / "assets" / "references" / "characters" / "security_guard_01" / "front.jpg"),
                                "usage": "face",
                                "strength": "strict",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "attach_refs_test",
                        "meta": {"project_root": str(project_root)},
                        "planning": {
                            "frame_briefs_json_path": str(frame_briefs_path),
                            "reference_binding_report_path": str(report_path),
                        },
                        "scene_plan": {"scene_plan_path": str(scene_plan_path)},
                        "prompts": {
                            "subject_registry_path": str(subject_registry_path),
                            "reference_assets_manifest_path": str(assets_manifest_path),
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "attach_reference_assets.py"), "--project-json", str(project_json)],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertTrue(result.stdout.strip())
            updated = json.loads(frame_briefs_path.read_text(encoding="utf-8"))
            self.assertEqual(updated[0]["reference_ids"], ["ref_security_guard_01_front"])
            self.assertEqual(len(updated[0]["reference_images"]), 1)
            self.assertEqual(updated[1]["reference_ids"], [])
            self.assertEqual(updated[1]["reference_bindings"], [])

    def test_build_reference_prompt_pack_creates_generator_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            (project_root / "config").mkdir(parents=True, exist_ok=True)
            (project_root / "prompts").mkdir(parents=True, exist_ok=True)
            continuity_path = project_root / "config" / "continuity_entities.json"
            pack_path = project_root / "prompts" / "reference_prompt_pack.json"
            project_json = project_root / "project.json"
            continuity_path.write_text(
                json.dumps(
                    {
                        "character_profiles": [
                            {
                                "entity_id": "security_guard_01",
                                "role": "security guard",
                                "profile": "a security guard in his forties, dark navy suit, coiled earpiece, alert posture, black gloves",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "reference_prompt_pack_test",
                        "meta": {"project_root": str(project_root)},
                        "planning": {"continuity_map_json_path": str(continuity_path)},
                        "assets": {"character_references_root": str(project_root / "assets" / "references" / "characters")},
                        "prompts": {
                            "reference_prompt_pack_path": str(pack_path),
                        },
                        "logs": {"generation_report_path": str(project_root / "logs" / "generation_report.md")},
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_reference_prompt_pack.py"), "--project-json", str(project_json)],
                check=True,
            )
            payload = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["shot_kind"], "identity_sheet")
            self.assertIn("single wide 16:9 frame", payload["items"][0]["prompt"])
            self.assertIn("front-facing chest-up portrait", payload["items"][0]["prompt"])
            self.assertIn("close-up of hands and sleeves", payload["items"][0]["prompt"])
            self.assertIn("full-body wardrobe view", payload["items"][0]["prompt"])

    def test_build_reference_prompt_pack_allows_empty_items_for_projects_without_recurring_people(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            (project_root / "config").mkdir(parents=True, exist_ok=True)
            (project_root / "prompts").mkdir(parents=True, exist_ok=True)
            continuity_path = project_root / "config" / "continuity_entities.json"
            pack_path = project_root / "prompts" / "reference_prompt_pack.json"
            project_json = project_root / "project.json"
            continuity_path.write_text(json.dumps({"character_profiles": []}), encoding="utf-8")
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "reference_prompt_pack_empty_test",
                        "meta": {"project_root": str(project_root)},
                        "planning": {"continuity_map_json_path": str(continuity_path)},
                        "assets": {"character_references_root": str(project_root / "assets" / "references" / "characters")},
                        "prompts": {"reference_prompt_pack_path": str(pack_path)},
                        "logs": {"generation_report_path": str(project_root / "logs" / "generation_report.md")},
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_reference_prompt_pack.py"), "--project-json", str(project_json)],
                check=True,
            )
            payload = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["items"], [])
            errors, warnings = validate_build_reference_prompt_pack(json.loads(project_json.read_text(encoding="utf-8")))
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_build_subject_registry_writes_reference_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            subject_dir = project_root / "assets" / "references" / "characters" / "security_guard_01"
            (project_root / "config").mkdir(parents=True, exist_ok=True)
            (project_root / "prompts").mkdir(parents=True, exist_ok=True)
            subject_dir.mkdir(parents=True, exist_ok=True)
            (subject_dir / "identity_sheet.png").write_bytes(b"fake")
            continuity_path = project_root / "config" / "continuity_entities.json"
            registry_path = project_root / "prompts" / "subject_registry.json"
            assets_path = project_root / "prompts" / "reference_assets.json"
            mapping_path = project_root / "prompts" / "fastgen_ref_paths.json"
            project_json = project_root / "project.json"
            continuity_path.write_text(
                json.dumps(
                    {
                        "character_profiles": [
                            {
                                "entity_id": "security_guard_01",
                                "role": "security guard",
                                "profile": "a security guard in his forties, dark navy suit, alert posture",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "subject_registry_mapping_test",
                        "meta": {"project_root": str(project_root)},
                        "planning": {"continuity_map_json_path": str(continuity_path)},
                        "assets": {"character_references_root": str(project_root / "assets" / "references" / "characters")},
                        "prompts": {
                            "subject_registry_path": str(registry_path),
                            "reference_assets_manifest_path": str(assets_path),
                            "reference_mapping_path": str(mapping_path),
                        },
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_subject_registry.py"), "--project-json", str(project_json)],
                check=True,
            )
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
            self.assertIn("ref_security_guard_01_identity_sheet", mapping)


if __name__ == "__main__":
    unittest.main()
