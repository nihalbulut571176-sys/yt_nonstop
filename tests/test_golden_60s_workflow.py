import base64
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

from yt_nonstop.pipeline.project_status import build_project_status


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SAMPLE_ROOT = ROOT / "sample_projects" / "golden_60s"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class Golden60sWorkflowTests(unittest.TestCase):
    TINY_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9uoAAAAASUVORK5CYII="
    )

    def write_png(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if Image is not None:
            image = Image.new("RGB", (96, 96), color=(120, 120, 120))
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
            "YT_NONSTOP_LLM_PROVIDER_MODE",
            "YT_NONSTOP_LLM_PROVIDER_COMMAND",
        ]:
            env.pop(key, None)
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT / "scripts"), env.get("PYTHONPATH", "")]).strip(os.pathsep)
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

    def hydrate_project(self, tmp_root: Path) -> Path:
        project_root = tmp_root / "golden_60s"
        shutil.copytree(SAMPLE_ROOT, project_root)
        for folder in [
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

        project_json = project_root / "project.json"
        project = json.loads(project_json.read_text(encoding="utf-8"))
        project.setdefault("profile_id", "fastgen_only")
        project["meta"]["project_root"] = str(project_root)
        project.setdefault("prompts", {})
        project["prompts"].setdefault("style_preset", "cinematic-realistic-v1")
        project["prompts"].setdefault("prompt_language", "English")
        project["prompts"].setdefault("authoring_model", "codex-gpt-5")
        project.setdefault("images", {})
        project["images"]["run_manifest_path"] = str(project_root / "images" / "fake_run" / "run_manifest.json")
        project["images"]["raw_images_dir"] = str(project_root / "images" / "fake_run")
        project["images"]["normalized_images_dir"] = str(project_root / "images" / "fake_run")
        audio_path = project_root / "audio" / "fake_audio.mp3"
        audio_path.write_bytes(b"golden sample fake audio")
        project["inputs"]["audio_path"] = str(audio_path)
        project["inputs"]["audio_duration_seconds"] = 78.0
        project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        srt_path = project_root / "input" / "source.srt"
        shutil.copyfile(srt_path, project_root / "transcript" / "cleaned.srt")
        scenes = [
            ("scene_0001", 1, 0.0, 10.0, "The investigators pin the first route across the floor plan and mark the cameras that saw it.", "route board establishes the first route", "floor plan with camera markers and red route pins"),
            ("scene_0002", 2, 10.0, 20.0, "A tray of receipts explains why the first ten minutes matter more than the rest of the night.", "receipts clarify the first ten minutes", "receipt tray, timestamp cards, stopwatch on evidence table"),
            ("scene_0003", 3, 20.0, 30.0, "The second corridor narrows toward the exit and forces the team to compare two competing timelines.", "corridor comparison creates the second route question", "narrow corridor map and twin timeline strips"),
            ("scene_0004", 4, 30.0, 40.0, "One still frame shows the guard turning away just before the missing interval begins.", "guard turns away before the gap begins", "monitor still of a guard turning away near a marked camera feed"),
            ("scene_0005", 5, 40.0, 50.0, "The evidence board isolates a silent gap where the package changes hands off camera.", "board isolates the silent handoff gap", "evidence board with a highlighted handoff gap and missing package marker"),
            ("scene_0006", 6, 50.0, 60.0, "A second map redraws the route in reverse to prove the return path was shorter than expected.", "reverse route redraw proves the short return path", "reverse route map with shorter return line"),
            ("scene_0007", 7, 60.0, 69.0, "The team compares timestamps from the loading door and the boutique alarm panel.", "timestamp comparison links loading door and alarm panel", "loading door timestamp card beside boutique alarm panel log"),
            ("scene_0008", 8, 69.0, 78.0, "The final board leaves one narrow interval highlighted as the only remaining unanswered gap.", "final board highlights the unanswered interval", "final board with one narrow interval highlighted in red"),
        ]
        scene_payload = {
            "project_id": "golden_60s",
            "scene_count": len(scenes),
            "source_srt_path": str(project_root / "transcript" / "cleaned.srt"),
            "scenes": [],
        }
        storyboard_items = []
        for scene_id, index, start, end, voice_text, visual_goal, what_is_in_frame in scenes:
            scene_payload["scenes"].append(
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
            storyboard_items.append(
                {
                    "segment_id": index,
                    "storyboard_id": f"SB{index:04d}",
                    "semantic_unit_id": f"SU{index:04d}",
                    "visual_role": "evidence",
                    "shot_function": "show concrete evidence",
                    "source_stage": "golden_60s_fixture",
                    "camera_storyboard": "stable documentary evidence framing",
                    "composition_progression": "layered evidence layout with clear subject separation",
                }
            )
        (project_root / "scene_plan" / "scene_plan.json").write_text(
            json.dumps(scene_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
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
                    "project_id": "golden_60s",
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
        return project_json

    def write_visual_allocation_seed(self, project_root: Path, beats: list[dict]) -> Path:
        def beat(index: int) -> dict:
            return beats[index - 1]

        slots = [
            {"visual_slot_id": "VS0001", "beat_ids": [beat(1)["beat_id"]], "scene_ids": [beat(1)["scene_id"]], "source_scene_id": beat(1)["scene_id"], "start": 0.0, "end": 5.0, "slot_type": "establishing_shot", "generation_decision": "new_image", "priority": "low", "variant_count": 1, "must_show": ["floor plan with camera markers and red route pins"], "visualized_claim": "route board establishes the first route", "film_block_id": "evidence_room", "camera": "stable documentary wide frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0002", "beat_ids": [beat(1)["beat_id"]], "scene_ids": [beat(1)["scene_id"]], "source_scene_id": beat(1)["scene_id"], "start": 5.0, "end": 10.0, "slot_type": "continuation_motion", "generation_decision": "hold_previous", "priority": "low", "variant_count": 0, "must_show": ["same floor plan and red route pins held on screen"], "visualized_claim": "the held route board continues the first route beat", "source_visual_slot_id": "VS0001", "film_block_id": "evidence_room", "camera": "stable documentary wide frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0003", "beat_ids": [beat(2)["beat_id"]], "scene_ids": [beat(2)["scene_id"]], "source_scene_id": beat(2)["scene_id"], "start": 10.0, "end": 20.0, "slot_type": "detail_insert", "generation_decision": "detail_insert", "priority": "low", "variant_count": 1, "must_show": ["receipt tray, timestamp cards, stopwatch on evidence table"], "visualized_claim": "receipts clarify the first ten minutes", "film_block_id": "evidence_room", "camera": "stable documentary close detail frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0004", "beat_ids": [beat(3)["beat_id"]], "scene_ids": [beat(3)["scene_id"]], "source_scene_id": beat(3)["scene_id"], "start": 20.0, "end": 30.0, "slot_type": "context_detail", "generation_decision": "new_angle_same_setup", "priority": "low", "variant_count": 1, "must_show": ["narrow corridor map and twin timeline strips"], "visualized_claim": "corridor comparison creates the second route question", "film_block_id": "evidence_room", "camera": "stable documentary corridor frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0005", "beat_ids": [beat(4)["beat_id"]], "scene_ids": [beat(4)["scene_id"]], "source_scene_id": beat(4)["scene_id"], "start": 30.0, "end": 40.0, "slot_type": "reaction_shot", "generation_decision": "reaction_shot", "priority": "low", "variant_count": 1, "must_show": ["monitor still of a guard turning away near a marked camera feed"], "visualized_claim": "guard turns away before the gap begins", "film_block_id": "evidence_room", "camera": "stable documentary monitor frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0006", "beat_ids": [beat(5)["beat_id"]], "scene_ids": [beat(5)["scene_id"]], "source_scene_id": beat(5)["scene_id"], "start": 40.0, "end": 50.0, "slot_type": "evidence_insert", "generation_decision": "new_image", "priority": "low", "variant_count": 1, "must_show": ["evidence board with a highlighted handoff gap and missing package marker"], "visualized_claim": "board isolates the silent handoff gap", "film_block_id": "evidence_room", "camera": "stable documentary evidence-board frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0007", "beat_ids": [beat(6)["beat_id"]], "scene_ids": [beat(6)["scene_id"]], "source_scene_id": beat(6)["scene_id"], "start": 50.0, "end": 60.0, "slot_type": "context_detail", "generation_decision": "new_angle_same_setup", "priority": "low", "variant_count": 1, "must_show": ["reverse route map with shorter return line"], "visualized_claim": "reverse route redraw proves the short return path", "film_block_id": "evidence_room", "camera": "stable documentary reverse-route frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0008", "beat_ids": [beat(7)["beat_id"]], "scene_ids": [beat(7)["scene_id"]], "source_scene_id": beat(7)["scene_id"], "start": 60.0, "end": 69.0, "slot_type": "detail_insert", "generation_decision": "detail_insert", "priority": "low", "variant_count": 1, "must_show": ["loading door timestamp card beside boutique alarm panel log"], "visualized_claim": "timestamp comparison links loading door and alarm panel", "film_block_id": "evidence_room", "camera": "stable documentary timestamp detail", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0009", "beat_ids": [beat(8)["beat_id"]], "scene_ids": [beat(8)["scene_id"]], "source_scene_id": beat(8)["scene_id"], "start": 69.0, "end": 73.5, "slot_type": "evidence_insert", "generation_decision": "new_image", "priority": "low", "variant_count": 1, "must_show": ["final board with one narrow interval highlighted in red"], "visualized_claim": "final board highlights the unanswered interval", "film_block_id": "evidence_room", "camera": "stable documentary evidence-board frame", "lighting": "motivated soft practical lighting"},
            {"visual_slot_id": "VS0010", "beat_ids": [beat(8)["beat_id"]], "scene_ids": [beat(8)["scene_id"]], "source_scene_id": beat(8)["scene_id"], "start": 73.5, "end": 78.0, "slot_type": "detail_insert", "generation_decision": "detail_insert", "priority": "low", "variant_count": 1, "must_show": ["tight highlighted interval at the edge of the final board"], "visualized_claim": "the unanswered interval is isolated in close detail", "film_block_id": "evidence_room", "camera": "stable documentary close detail frame", "lighting": "motivated soft practical lighting"},
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
            if item["scene_id"] == "scene_0002":
                prompt = "Premium documentary still with moody atmosphere and abstract investigative tension."
            else:
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
                    "voiceover_summary": "golden 60s no-api prompt draft",
                    "reference_ids": [],
                    "continuity_mode": "locked",
                    "event_clarity_required": False,
                    "event_type": "evidence_visual",
                    "event_priority_reason": "golden sample coverage",
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
                    "job_id": "golden-60s-fake-job",
                    "scene_id": scene_id,
                    "frame_id": row["frame_id"],
                    "source_prompt_index": index,
                    "variant_index": 1,
                    "variant_label": "V01",
                    "prompt_hash": f"golden_hash_{index:04d}",
                    "generator_profile": "fake_no_api",
                    "created_at": "2026-05-29T00:00:00Z",
                    "status": "success",
                    "image_path": str(image_path),
                    "normalized_image_path": str(image_path),
                    "variant_count": int(row.get("variant_count", 1) or 1),
                }
            )
        (images_dir / "run_manifest.json").write_text(
            json.dumps({"job_id": "golden-60s-fake-job", "generated_images": generated}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_golden_60s_full_no_api_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.hydrate_project(Path(tmp))
            project_root = project_json.parent

            self.run_script(project_json, "build_narration_beats.py")
            self.run_script(project_json, "author_narration_beats.py", "--provider", "heuristic")
            beats = json.loads((project_root / "planning" / "narration_beats.json").read_text(encoding="utf-8"))["beats"]
            self.assertEqual(len(beats), 8)

            visual_allocation_seed = self.write_visual_allocation_seed(project_root, beats)
            self.run_script(project_json, "author_visual_allocation_plan.py", "--provider", "file", "--input-json", str(visual_allocation_seed))
            self.run_script(project_json, "estimate_project_generation.py")
            self.run_script(project_json, "build_visual_shot_plan.py")
            self.run_script(project_json, "build_frame_briefs.py")

            drafts_path = self.write_fake_prompt_drafts(project_root)
            self.run_script(project_json, "apply_llm_prompt_drafts.py", "--drafts-json", str(drafts_path))
            self.run_script(project_json, "generation_lock.py")
            self.run_script(project_json, "export_generation_batches.py")

            allocation = json.loads((project_root / "planning" / "visual_allocation_plan.json").read_text(encoding="utf-8"))
            self.assertGreater(allocation["metrics"]["visual_slots_count"], allocation["metrics"]["narration_beats_count"])
            self.assertGreaterEqual(allocation["metrics"]["hold_or_continuation_slots_count"], 1)

            locked_rows = json.loads((project_root / "prompts" / "generation_locked_frames.json").read_text(encoding="utf-8"))
            hold_rows = [row for row in locked_rows if row.get("generation_decision") == "hold_previous"]
            self.assertGreaterEqual(len(hold_rows), 1)

            batch_rows = json.loads((project_root / "exports" / "fastgen_prompts.batches.json").read_text(encoding="utf-8"))
            self.assertNotIn("hold_previous", {row.get("generation_decision") for row in batch_rows})
            self.assertNotIn(hold_rows[0]["frame_id"], {row.get("frame_id") for row in batch_rows})

            self.write_fake_generated_images(project_root)
            self.run_script(project_json, "qc_generated_images.py", "--semantic-qc-mode", "disabled")
            selected_manifest_path = project_root / "qc" / "selected_images_manifest.json"
            qc_report_path = project_root / "qc" / "image_qc_report.json"
            selected_payload = json.loads(selected_manifest_path.read_text(encoding="utf-8"))
            selected_payload["selected_images"][1]["selection_status"] = "manual_review"
            selected_payload["selected_images"][1]["coverage_status"] = "fail"
            selected_payload["selected_images"][1]["semantic_flags"] = ["must_show_not_grounded_in_prompt"]
            selected_manifest_path.write_text(json.dumps(selected_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            qc_payload = json.loads(qc_report_path.read_text(encoding="utf-8"))
            for row in qc_payload.get("images", []):
                if row.get("scene_id") == selected_payload["selected_images"][1]["scene_id"]:
                    row["decision"] = "manual_review"
                    row["coverage_status"] = "fail"
                    row["semantic_flags"] = ["must_show_not_grounded_in_prompt"]
            qc_report_path.write_text(json.dumps(qc_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.run_script(project_json, "build_regeneration_plan.py")
            self.run_script(project_json, "execute_regeneration_plan.py", "--mode", "fake")
            self.run_script(project_json, "build_continuity_qc.py")
            self.run_script(project_json, "build_review_package.py")

            review_decisions = {
                "decisions": [
                    {"scene_id": row["scene_id"], "status": "approve", "notes": "golden sample approval"}
                    for row in json.loads((project_root / "qc" / "selected_images_manifest.json").read_text(encoding="utf-8"))["selected_images"]
                ]
            }
            (project_root / "qc" / "review_decisions.json").write_text(
                json.dumps(review_decisions, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.run_script(project_json, "apply_review_decisions.py")
            self.run_script_in_process(project_json, "build_project_slideshow_timeline.py")
            self.run_script_in_process(project_json, "render_project_slideshow_video.py", "--dry-run")
            self.run_script_in_process(project_json, "build_production_report.py")

            regen_execution = json.loads((project_root / "qc" / "regeneration_execution_report.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(regen_execution["attempt_count"], 1)

            self.assertTrue((project_root / "qc" / "review_package.html").exists())
            self.assertTrue((project_root / "renders" / "edit_decision_list.json").exists())
            self.assertTrue((project_root / "logs" / "render_report.json").exists())
            self.assertTrue((project_root / "reports" / "production_report.md").exists())

            dashboard = build_project_status(project_json)
            self.assertTrue(bool(dashboard.next_command) or dashboard.completed)


if __name__ == "__main__":
    unittest.main()
