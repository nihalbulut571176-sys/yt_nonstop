import base64
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class NoApiE2ESmokeTests(unittest.TestCase):
    TINY_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9uoAAAAASUVORK5CYII="
    )

    def write_png(self, path: Path) -> None:
        if Image is not None:
            image = Image.new("RGB", (64, 64), color=(120, 120, 120))
            image.save(path)
        else:  # pragma: no cover
            path.write_bytes(self.TINY_PNG)

    def run_script(self, project_json: Path, script_name: str, *args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        for key in [
            "OPENAI_API_KEY",
            "FASTGEN_API_KEY",
            "HEYGEN_API_KEY",
            "VEONONSTOP_API_KEY",
            "YT_NONSTOP_BEAT_AUTHORING_PROVIDER",
            "YT_NONSTOP_VISUAL_ALLOCATION_PROVIDER",
            "YT_NONSTOP_IMAGE_SEMANTIC_QC_MODE",
        ]:
            env.pop(key, None)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script_name), "--project-json", str(project_json), *args],
            check=True,
            timeout=30,
            env=env,
        )

    def run_script_in_process(self, project_json: Path, script_name: str, *args: str) -> None:
        old_argv = sys.argv[:]
        try:
            sys.argv = [script_name, "--project-json", str(project_json), *args]
            runpy.run_path(str(SCRIPTS / script_name), run_name="__main__")
        finally:
            sys.argv = old_argv

    @staticmethod
    def rewrite_paths(obj, sample_root: str, project_root: Path):
        if isinstance(obj, dict):
            return {key: NoApiE2ESmokeTests.rewrite_paths(value, sample_root, project_root) for key, value in obj.items()}
        if isinstance(obj, list):
            return [NoApiE2ESmokeTests.rewrite_paths(item, sample_root, project_root) for item in obj]
        if isinstance(obj, str):
            return obj.replace(sample_root, str(project_root))
        return obj

    def build_project_fixture(self, tmp_root: Path) -> Path:
        project_root = tmp_root / "project"
        for folder in [
            "input",
            "audio",
            "transcript",
            "scene_plan",
            "prompts",
            "planning",
            "exports",
            "reports",
            "logs",
            "config",
            Path("images") / "fake_run",
            "qc",
            "renders",
        ]:
            (project_root / folder).mkdir(parents=True, exist_ok=True)

        sample_root = r"C:\Users\MIKE\Documents\Codex\YT\projects\telegram_darknet_001"
        project = json.loads((ROOT / "deliverables" / "project.template.json").read_text(encoding="utf-8"))
        project = self.rewrite_paths(project, sample_root, project_root)
        project["project_id"] = "no_api_e2e_smoke"
        project["meta"]["project_root"] = str(project_root)
        project["meta"]["language"] = "en"
        project["status"] = "draft"
        project["current_stage"] = "build_narration_beats"
        project["workflow"].update(
            {
                "is_sequence": True,
                "skip_storyboard_allowed": False,
                "strict_generation_lock": False,
                "render_dry_run": True,
                "profile": "no_api_smoke",
            }
        )
        project["planning"]["visual_allocation_provider"] = "file"
        project.setdefault("qc", {})
        project.setdefault("generation", {})
        project["qc"].update({"image_semantic_qc_mode": "disabled", "allow_manual_review_without_vlm": True})
        project["generation"].update({"key_beat_variants": 1, "normal_beat_variants": 1, "allow_regeneration": True})

        audio_path = project_root / "audio" / "fake_audio.mp3"
        audio_path.write_bytes(b"fake audio for render dry run only")
        project["inputs"]["audio_path"] = str(audio_path)
        project["inputs"]["audio_duration_seconds"] = 12.0
        project["transcription"]["audio_path"] = str(audio_path)

        srt_path = project_root / "transcript" / "cleaned.srt"
        srt_path.write_text(
            "\n\n".join(
                [
                    "1\n00:00:00,000 --> 00:00:04,000\nThe investigators reconstruct the first route through the store.",
                    "2\n00:00:04,000 --> 00:00:07,000\nA table of receipts explains why the timing matters.",
                    "3\n00:00:07,000 --> 00:00:10,000\nThe camera follows the second corridor toward the exit.",
                    "4\n00:00:10,000 --> 00:00:12,000\nThe final board shows the missing interval.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        project["scene_plan"]["source_srt_path"] = str(srt_path)
        project["transcription"]["srt_path"] = str(srt_path)
        project["transcription"]["raw_srt_path"] = str(srt_path)
        project["transcript_cleanup"]["cleaned_srt_path"] = str(srt_path)

        scene_specs = [
            (
                "scene_0001",
                1,
                0.0,
                4.0,
                "The investigators reconstruct the first route through the store.",
                "forensic desk route reconstruction",
                "forensic desk with four map sheets and red route pins",
            ),
            (
                "scene_0002",
                2,
                4.0,
                7.0,
                "A table of receipts explains why the timing matters.",
                "receipt evidence explains the timing gap",
                "receipt evidence table with timestamp cards and a stopwatch",
            ),
            (
                "scene_0003",
                3,
                7.0,
                10.0,
                "The camera follows the second corridor toward the exit.",
                "corridor movement reveals the exit path",
                "empty corridor with floor arrows leading toward a glass exit",
            ),
            (
                "scene_0004",
                4,
                10.0,
                12.0,
                "The final board shows the missing interval.",
                "timeline board isolates the missing interval",
                "investigation board with clock photos and a highlighted time gap",
            ),
        ]
        scenes = []
        for scene_id, index, start, end, voice_text, visual_goal, what_is_in_frame in scene_specs:
            scenes.append(
                {
                    "scene_id": scene_id,
                    "shot_index": index,
                    "source_segment_id": index,
                    "source_index": index,
                    "part_index": 1,
                    "parts_total": 1,
                    "start": start,
                    "end": end,
                    "duration": round(end - start, 3),
                    "voice_text": voice_text,
                    "scene_summary": voice_text,
                    "scene_meaning": visual_goal,
                    "narrative_purpose": "show a concrete investigative clue",
                    "visual_goal": visual_goal,
                    "visual_function": "evidence",
                    "visual_strategy": "literal_premium",
                    "visual_idea": what_is_in_frame,
                    "main_subject": what_is_in_frame,
                    "primary_subject": what_is_in_frame,
                    "what_is_in_frame": what_is_in_frame,
                    "environment": "controlled documentary investigation room",
                    "composition": "grounded documentary evidence layout",
                    "camera": "stable documentary camera",
                    "lighting": "motivated soft practical lighting",
                    "scene_importance": "supporting",
                    "event_clarity_required": False,
                    "reference_ids": [],
                    "reference_bindings": [],
                    "subject_ids": [],
                    "mentioned_subject_ids": [],
                    "visible_subject_ids": [],
                    "active_entity_ids": [],
                    "negative_prompt": "logos, watermarks, subtitles, labels",
                    "notes": [],
                }
            )
        scene_plan_path = project_root / "scene_plan" / "scene_plan.json"
        scene_plan_path.write_text(
            json.dumps(
                {
                    "project_id": project["project_id"],
                    "schema_version": project["schema_version"],
                    "source_srt_path": str(srt_path),
                    "scene_count": len(scenes),
                    "scenes": scenes,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        project["scene_plan"]["scene_plan_path"] = str(scene_plan_path)
        project["scene_plan"]["scene_count"] = len(scenes)

        storyboard_items = []
        for scene in scenes:
            segment_id = scene["source_segment_id"]
            storyboard_items.append(
                {
                    "segment_id": segment_id,
                    "storyboard_id": f"SB{segment_id:04d}",
                    "semantic_unit_id": f"SU{segment_id:04d}",
                    "visual_role": "evidence",
                    "shot_function": "show concrete evidence",
                    "source_stage": "no_api_smoke_fixture",
                    "camera_storyboard": "stable documentary evidence framing",
                    "composition_progression": "layered evidence layout with clear subject separation",
                }
            )
        (project_root / "planning" / "storyboard.json").write_text(
            json.dumps({"items": storyboard_items}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (project_root / "config" / "continuity_entities.json").write_text(
            json.dumps({"scene_entity_map": {}, "segment_entity_map": {}}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (project_root / "prompts" / "subject_registry.json").write_text(
            json.dumps({"subjects": []}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (project_root / "prompts" / "visual_bible.json").write_text(
            json.dumps(
                {
                    "project_id": project["project_id"],
                    "main_subject": "documentary evidence investigation",
                    "subject_type": "investigation",
                    "visual_world": "controlled documentary investigation room",
                    "continuity_rules": ["keep the same grounded evidence-room realism"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        project["images"]["run_manifest_path"] = str(project_root / "images" / "fake_run" / "run_manifest.json")
        project["images"]["raw_images_dir"] = str(project_root / "images" / "fake_run")
        project["images"]["normalized_images_dir"] = str(project_root / "images" / "fake_run")

        project_json = project_root / "project.json"
        project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return project_json

    def write_visual_allocation_seed(self, project_root: Path, beats: list[dict]) -> Path:
        def beat(index: int) -> dict:
            return beats[index - 1]

        slots = [
            {
                "visual_slot_id": "VS0001",
                "beat_ids": [beat(1)["beat_id"]],
                "scene_ids": [beat(1)["scene_id"]],
                "source_scene_id": beat(1)["scene_id"],
                "start": 0.0,
                "end": 2.0,
                "slot_type": "establishing_shot",
                "generation_decision": "new_image",
                "priority": "low",
                "variant_count": 1,
                "must_show": ["forensic desk with four map sheets and red route pins"],
                "visualized_claim": "forensic desk route reconstruction",
                "film_block_id": "evidence_room",
                "camera": "stable documentary wide frame",
                "lighting": "motivated soft practical lighting",
            },
            {
                "visual_slot_id": "VS0002",
                "beat_ids": [beat(1)["beat_id"]],
                "scene_ids": [beat(1)["scene_id"]],
                "source_scene_id": beat(1)["scene_id"],
                "start": 2.0,
                "end": 4.0,
                "slot_type": "continuation_motion",
                "generation_decision": "hold_previous",
                "priority": "low",
                "variant_count": 0,
                "must_show": ["same forensic desk angle held while red route pins remain fixed"],
                "visualized_claim": "held evidence frame continues the route reconstruction",
                "source_visual_slot_id": "VS0001",
                "film_block_id": "evidence_room",
                "camera": "stable documentary wide frame",
                "lighting": "motivated soft practical lighting",
            },
            {
                "visual_slot_id": "VS0003",
                "beat_ids": [beat(2)["beat_id"]],
                "scene_ids": [beat(2)["scene_id"]],
                "source_scene_id": beat(2)["scene_id"],
                "start": 4.0,
                "end": 7.0,
                "slot_type": "detail_insert",
                "generation_decision": "detail_insert",
                "priority": "low",
                "variant_count": 1,
                "must_show": ["receipt evidence table with timestamp cards and a stopwatch"],
                "visualized_claim": "receipt evidence explains the timing gap",
                "film_block_id": "evidence_room",
                "camera": "stable documentary close detail frame",
                "lighting": "motivated soft practical lighting",
            },
            {
                "visual_slot_id": "VS0004",
                "beat_ids": [beat(3)["beat_id"]],
                "scene_ids": [beat(3)["scene_id"]],
                "source_scene_id": beat(3)["scene_id"],
                "start": 7.0,
                "end": 10.0,
                "slot_type": "context_detail",
                "generation_decision": "new_angle_same_setup",
                "priority": "low",
                "variant_count": 1,
                "must_show": ["empty corridor with floor arrows leading toward a glass exit"],
                "visualized_claim": "corridor movement reveals the exit path",
                "film_block_id": "evidence_room",
                "camera": "stable documentary corridor frame",
                "lighting": "motivated soft practical lighting",
            },
            {
                "visual_slot_id": "VS0005",
                "beat_ids": [beat(4)["beat_id"]],
                "scene_ids": [beat(4)["scene_id"]],
                "source_scene_id": beat(4)["scene_id"],
                "start": 10.0,
                "end": 12.0,
                "slot_type": "evidence_insert",
                "generation_decision": "new_image",
                "priority": "low",
                "variant_count": 1,
                "must_show": ["investigation board with clock photos and a highlighted time gap"],
                "visualized_claim": "timeline board isolates the missing interval",
                "film_block_id": "evidence_room",
                "camera": "stable documentary evidence-board frame",
                "lighting": "motivated soft practical lighting",
            },
        ]
        path = project_root / "planning" / "visual_allocation_seed.json"
        path.write_text(json.dumps({"visual_slots": slots}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_fake_prompt_drafts(self, project_root: Path) -> Path:
        prompt_package = json.loads((project_root / "prompts" / "prompt_package.json").read_text(encoding="utf-8"))
        drafts = []
        for item in prompt_package["items"]:
            must_show = [str(value) for value in item.get("must_show", []) if str(value).strip()]
            must_show_text = must_show[0] if must_show else str(item.get("screen_action") or "documentary evidence object")
            visualized_claim = str(item.get("visualized_claim") or "concrete evidence beat")
            prompt = (
                f"Premium documentary still inside a controlled evidence room: {must_show_text}. "
                f"The image visibly supports this claim: {visualized_claim}. "
                "Use grounded real-world materials, natural shadows, layered depth, clean composition, "
                "and a silent investigative mood with no logos or subtitles."
            )
            drafts.append(
                {
                    "scene_id": item["scene_id"],
                    "frame_id": item["frame_id"],
                    "beat_id": item["beat_id"],
                    "scene_meaning": visualized_claim,
                    "narrative_purpose": "make the narration visually concrete",
                    "viewer_emotion": "focused curiosity",
                    "visual_function": item.get("visual_function") or item.get("visual_role") or "evidence",
                    "visual_strategy": "literal_premium",
                    "visual_idea": must_show_text,
                    "main_subject": must_show_text,
                    "environment": "controlled documentary evidence room",
                    "visual_goal": visualized_claim,
                    "draft_prompt": prompt,
                    "final_prompt": prompt,
                    "scene_importance": item.get("beat_priority", "supporting"),
                    "shot_id": item.get("shot_id", ""),
                    "source_shot_id": item.get("source_shot_id", ""),
                    "generation_mode": item.get("generation_mode", "new_image"),
                    "variation_note": item.get("variation_note", ""),
                    "shot_type": item.get("shot_type", "medium documentary shot"),
                    "transition_in": item.get("transition_in", "cut"),
                    "transition_out": item.get("transition_out", "cut_on_phrase_end"),
                    "film_block_id": item.get("film_block_id", "evidence_room"),
                    "shot_role": item.get("visual_role", "evidence"),
                    "primary_subject": must_show_text,
                    "secondary_subjects": [],
                    "what_is_in_frame": must_show_text,
                    "visualized_claim": visualized_claim,
                    "must_show": must_show,
                    "camera": item.get("camera", "stable documentary camera"),
                    "composition": "layered evidence-room composition",
                    "lighting": item.get("lighting", "motivated soft practical lighting"),
                    "mood": "quiet investigative tension",
                    "continuity_notes": "Keep the same evidence room, grounded materials, and documentary realism.",
                    "active_entity_ids": [],
                    "continuity_cast": [],
                    "voiceover_summary": "local no-api smoke-test prompt draft",
                    "reference_ids": [],
                    "continuity_mode": "locked",
                    "event_clarity_required": False,
                    "event_type": "evidence_visual",
                    "event_priority_reason": "smoke test coverage",
                    "negative_prompt": "logos, watermarks, subtitles, labels",
                    "beat_priority": item.get("beat_priority", "supporting"),
                    "key_beat": bool(item.get("key_beat", False)),
                    "variant_count": int(item.get("variant_count", 1) or 0),
                }
            )
        path = project_root / "prompts" / "llm_prompt_drafts.json"
        path.write_text(json.dumps(drafts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_fake_generated_images(self, project_root: Path) -> None:
        batch_rows = json.loads((project_root / "exports" / "fastgen_prompts.batches.json").read_text(encoding="utf-8"))
        locked_rows = json.loads((project_root / "prompts" / "generation_locked_frames.json").read_text(encoding="utf-8"))
        scene_id_by_frame = {row["frame_id"]: row["scene_id"] for row in locked_rows if row.get("frame_id") and row.get("scene_id")}
        images_dir = project_root / "images" / "fake_run"
        images_dir.mkdir(parents=True, exist_ok=True)
        generated = []
        for index, row in enumerate(batch_rows, start=1):
            scene_id = scene_id_by_frame[row["frame_id"]]
            image_path = images_dir / f"{scene_id}_V01.png"
            self.write_png(image_path)
            generated.append(
                {
                    "job_id": "no-api-smoke-job",
                    "scene_id": scene_id,
                    "frame_id": row["frame_id"],
                    "source_prompt_index": index,
                    "variant_index": 1,
                    "variant_label": "V01",
                    "prompt_hash": f"fake_hash_{index:04d}",
                    "generator_profile": "fake_no_api",
                    "created_at": "2026-05-28T00:00:00Z",
                    "status": "success",
                    "image_path": str(image_path),
                    "normalized_image_path": str(image_path),
                    "variant_count": int(row.get("variant_count", 1) or 1),
                }
            )
        (images_dir / "run_manifest.json").write_text(
            json.dumps({"job_id": "no-api-smoke-job", "generated_images": generated}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_full_no_api_smoke_pipeline_keeps_visual_slot_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.build_project_fixture(Path(tmp))
            project_root = project_json.parent

            self.run_script(project_json, "build_narration_beats.py")
            self.run_script(project_json, "author_narration_beats.py", "--provider", "heuristic")

            beats = json.loads((project_root / "planning" / "narration_beats.json").read_text(encoding="utf-8"))["beats"]
            self.assertGreaterEqual(len(beats), 3)
            self.assertLessEqual(len(beats), 5)

            visual_allocation_seed = self.write_visual_allocation_seed(project_root, beats)
            self.run_script(project_json, "author_visual_allocation_plan.py", "--provider", "file", "--input-json", str(visual_allocation_seed))
            self.run_script(project_json, "build_visual_shot_plan.py")
            self.run_script(project_json, "build_frame_briefs.py")

            drafts_path = self.write_fake_prompt_drafts(project_root)
            self.run_script(project_json, "apply_llm_prompt_drafts.py", "--drafts-json", str(drafts_path))
            self.run_script(project_json, "generation_lock.py")
            self.run_script(project_json, "export_generation_batches.py")

            allocation = json.loads((project_root / "planning" / "visual_allocation_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(allocation["metrics"]["narration_beats_count"], 4)
            self.assertEqual(allocation["metrics"]["visual_slots_count"], 5)
            self.assertGreater(allocation["metrics"]["visual_slots_count"], allocation["metrics"]["narration_beats_count"])
            self.assertEqual(allocation["metrics"]["hold_or_continuation_slots_count"], 1)

            locked_rows = json.loads((project_root / "prompts" / "generation_locked_frames.json").read_text(encoding="utf-8"))
            hold_rows = [row for row in locked_rows if row.get("generation_decision") == "hold_previous"]
            self.assertEqual(len(hold_rows), 1)

            batch_rows = json.loads((project_root / "exports" / "fastgen_prompts.batches.json").read_text(encoding="utf-8"))
            self.assertEqual(len(batch_rows), 4)
            self.assertNotIn("hold_previous", {row.get("generation_decision") for row in batch_rows})
            self.assertNotIn(hold_rows[0]["frame_id"], {row.get("frame_id") for row in batch_rows})

            batch_meta = json.loads((project_root / "exports" / "fastgen_prompts.md.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(batch_meta["prompt_count"], 4)
            self.assertEqual(batch_meta["non_generative_frame_count"], 1)

            self.write_fake_generated_images(project_root)
            self.run_script(project_json, "qc_generated_images.py", "--semantic-qc-mode", "disabled")
            self.run_script(project_json, "build_regeneration_plan.py")
            self.run_script(project_json, "build_continuity_qc.py")
            self.run_script_in_process(project_json, "build_project_slideshow_timeline.py")
            self.run_script_in_process(project_json, "render_project_slideshow_video.py", "--dry-run")
            self.run_script_in_process(project_json, "build_production_report.py")

            selected = json.loads((project_root / "qc" / "selected_images_manifest.json").read_text(encoding="utf-8"))["selected_images"]
            self.assertEqual(len(selected), 4)
            self.assertNotIn(hold_rows[0]["scene_id"], {row["scene_id"] for row in selected})

            regen = json.loads((project_root / "qc" / "regeneration_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(regen["tasks"], [])

            timeline = json.loads((project_root / "renders" / "slideshow_timeline.json").read_text(encoding="utf-8"))
            self.assertEqual(len(timeline), 5)
            hold_timeline = next(row for row in timeline if row["generation_decision"] == "hold_previous")
            previous_timeline = timeline[timeline.index(hold_timeline) - 1]
            self.assertEqual(hold_timeline["image"], previous_timeline["image"])
            self.assertIn(hold_timeline["motion_type"], {"subtle_push_in", "slow_push_in", "static_hold"})

            edl = json.loads((project_root / "renders" / "edit_decision_list.json").read_text(encoding="utf-8"))["edl"]
            self.assertEqual(len(edl), 5)
            for row in edl:
                self.assertIn("motion_type", row)
                self.assertIn("motion_intensity", row)
                self.assertIn("crop_anchor", row)
                self.assertIn("transition_style", row)
            establishing_row = next(row for row in edl if row["visual_slot_id"] == "VS0001")
            self.assertIn(establishing_row["motion_type"], {"slow_pan", "slow_push_in"})
            detail_row = next(row for row in edl if row["visual_slot_id"] == "VS0003")
            self.assertIn(detail_row["motion_type"], {"static_hold", "slight_push"})

            render_report = json.loads((project_root / "logs" / "render_report.json").read_text(encoding="utf-8"))
            self.assertTrue(render_report["dry_run"])
            self.assertEqual(render_report["status"], "dry_run")
            self.assertEqual(render_report["render_mode"], "motion_edl")
            self.assertTrue(render_report["motion_summary"]["enabled"])
            self.assertIn("filter_complex", " ".join(render_report["ffmpeg_command"]))

            production_report_path = project_root / "reports" / "production_report.json"
            self.assertTrue(production_report_path.exists())
            production_report = json.loads(production_report_path.read_text(encoding="utf-8"))
            self.assertEqual(production_report["metrics"]["narration_beats_count"], 4)
            self.assertEqual(production_report["metrics"]["visual_slots_count"], 5)
            self.assertEqual(production_report["metrics"]["hold_or_continuation_slots_count"], 1)
            self.assertTrue(production_report["metrics"]["render_ready"])


if __name__ == "__main__":
    unittest.main()
