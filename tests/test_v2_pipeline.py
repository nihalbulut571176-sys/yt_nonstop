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

from pipeline_contracts import contains_forbidden_terms, has_cyrillic, similarity_score  # noqa: E402
from project_pipeline_utils import load_project  # noqa: E402


class V2PipelineTests(unittest.TestCase):
    def build_project_fixture(self, root: Path, frame_count: int = 30, inject_mixed_paths: bool = False) -> Path:
        template = json.loads((ROOT / "deliverables" / "project.template.json").read_text(encoding="utf-8"))
        sample_root = r"C:\Users\MIKE\Documents\Codex\YT\projects\telegram_darknet_001"
        project_root = root / "project"
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
        ]:
            (project_root / folder).mkdir(parents=True, exist_ok=True)

        def rewrite_paths(obj):
            if isinstance(obj, dict):
                return {key: rewrite_paths(value) for key, value in obj.items()}
            if isinstance(obj, list):
                return [rewrite_paths(item) for item in obj]
            if isinstance(obj, str):
                return obj.replace(sample_root, str(project_root))
            return obj

        project = rewrite_paths(template)
        project["project_id"] = "v2_pipeline_test"
        project["meta"]["project_root"] = str(project_root)
        project["meta"]["language"] = "en"
        project["scene_plan"]["source_srt_path"] = str(project_root / "transcript" / "cleaned.srt")
        project["transcription"]["srt_path"] = str(project_root / "transcript" / "cleaned.srt")
        project["transcription"]["raw_srt_path"] = str(project_root / "transcript" / "cleaned.srt")
        if inject_mixed_paths:
            project["scene_plan"]["scene_plan_path"] = f"{project_root.as_posix()}\\scene_plan\\scene_plan.json"
            project["scene_plan"]["source_srt_path"] = f"{project_root.as_posix()}\\transcript\\cleaned.srt"
            project["transcription"]["srt_path"] = f"{project_root.as_posix()}\\transcript\\cleaned.srt"
            project["transcription"]["raw_srt_path"] = f"{project_root.as_posix()}\\transcript\\cleaned.srt"
            project["logs"]["pipeline_log_path"] = f"{project_root.as_posix()}\\logs\\pipeline.log"
            project["logs"]["events_jsonl_path"] = f"{project_root.as_posix()}\\logs\\events.jsonl"

        srt_blocks = []
        scenes = []
        for index in range(frame_count):
            start = float(index)
            end = float(index + 1)
            if index < 8:
                text = "Security camera watches the boutique door."
            elif index < 16:
                text = f"Investigators reconstruct delay point {index}."
            else:
                text = f"Forensic detail reveals sequence beat {index}."
            hh = "00"
            mm = "00"
            ss_start = f"{index:02d}"
            ss_end = f"{index + 1:02d}"
            srt_blocks.append(
                "\n".join(
                    [
                        str(index + 1),
                        f"{hh}:{mm}:{ss_start},000 --> {hh}:{mm}:{ss_end},000",
                        text,
                    ]
                )
            )
            scenes.append(
                {
                    "scene_id": f"scene_{index + 1:04d}",
                    "shot_index": index + 1,
                    "source_segment_id": index + 1,
                    "source_index": index + 1,
                    "part_index": 1,
                    "parts_total": 1,
                    "start": start,
                    "end": end,
                    "duration": 1.0,
                    "voice_text": text,
                    "scene_summary": text,
                    "scene_meaning": "",
                    "narrative_purpose": "",
                    "visual_goal": "",
                    "visual_reason": "",
                    "main_subject": "",
                    "negative_prompt": "",
                }
            )

        (project_root / "transcript" / "cleaned.srt").write_text("\n\n".join(srt_blocks) + "\n", encoding="utf-8")
        (project_root / "scene_plan" / "scene_plan.json").write_text(
            json.dumps({"scenes": scenes}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        project_json = project_root / "project.json"
        project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return project_json

    def run_pipeline(self, project_json: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline.py"), *args, "--project-json", str(project_json)],
            capture_output=True,
            text=True,
            check=True,
        )

    def run_validator(self, project_json: Path, stage: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_project.py"), "--project-json", str(project_json), "--stage", stage],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_load_project_adds_v2_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.build_project_fixture(Path(tmp), frame_count=4)
            project = load_project(project_json)
            self.assertTrue(project["planning"]["global_scene_plan_path"].endswith("global_scene_plan.json"))
            self.assertTrue(project["prompts"]["directors_cut_review_path"].endswith("directors_cut_review.json"))
            self.assertTrue(project["exports"]["generator_queue_csv_path"].endswith("generator_queue.csv"))
            self.assertTrue(project["reports"]["qc_report_md_path"].endswith("qc_report.md"))

    def test_load_project_rebases_template_and_mixed_paths_into_active_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.build_project_fixture(Path(tmp), frame_count=4, inject_mixed_paths=True)
            project = load_project(project_json)
            project_root = project_json.parent.resolve()
            stale_prefix = r"C:\Users\MIKE\Documents\Codex\YT\projects\telegram_darknet_001"

            self.assertEqual(Path(project["meta"]["project_root"]).resolve(), project_root)
            self.assertEqual(Path(project["scene_plan"]["scene_plan_path"]).resolve(), project_root / "scene_plan" / "scene_plan.json")
            self.assertEqual(Path(project["scene_plan"]["source_srt_path"]).resolve(), project_root / "transcript" / "cleaned.srt")
            self.assertEqual(Path(project["transcription"]["srt_path"]).resolve(), project_root / "transcript" / "cleaned.srt")
            self.assertEqual(Path(project["logs"]["pipeline_log_path"]).resolve(), project_root / "logs" / "pipeline.log")

            path_like_values: list[str] = []

            def collect_paths(payload):
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        if isinstance(value, str) and (key.endswith(("_path", "_dir", "_root")) or key == "audio_path"):
                            path_like_values.append(value)
                        else:
                            collect_paths(value)
                elif isinstance(payload, list):
                    for item in payload:
                        collect_paths(item)

            collect_paths(project)
            self.assertTrue(path_like_values)
            self.assertFalse(any(stale_prefix in value for value in path_like_values))

    def test_v2_pipeline_cli_builds_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.build_project_fixture(Path(tmp), frame_count=30, inject_mixed_paths=True)
            self.run_pipeline(project_json, "parse-srt")
            self.run_pipeline(project_json, "build-scenes", "--target-scenes", "5")
            self.run_pipeline(project_json, "build-subscenes")
            self.run_pipeline(project_json, "build-storyboard")
            self.run_pipeline(project_json, "directors-cut", "--chunk-size", "10")
            self.run_pipeline(project_json, "write-prompts")
            self.run_pipeline(project_json, "qc")
            self.run_pipeline(project_json, "rewrite-flagged")
            self.run_pipeline(project_json, "export-generator-queue")
            self.run_pipeline(project_json, "export-edit-timeline")
            self.run_pipeline(project_json, "make-test-batch", "--count", "10")

            self.run_validator(project_json, "build_storyboard")
            self.run_validator(project_json, "write_prompts")
            self.run_validator(project_json, "rewrite_flagged")
            self.run_validator(project_json, "export_generator_queue")
            self.run_validator(project_json, "export_edit_timeline")

            project = load_project(project_json)
            generator_queue = Path(project["exports"]["generator_queue_csv_path"])
            edit_timeline = Path(project["exports"]["edit_timeline_csv_path"])
            frame_timing = Path(project["exports"]["frame_timing_srt_path"])
            qc_report = Path(project["reports"]["qc_report_md_path"])
            test_batch = generator_queue.with_name("test_batch_10.csv")

            self.assertTrue(generator_queue.exists())
            self.assertTrue(edit_timeline.exists())
            self.assertTrue(frame_timing.exists())
            self.assertTrue(qc_report.exists())
            self.assertTrue(test_batch.exists())
            self.assertEqual(max(0, len(generator_queue.read_text(encoding="utf-8").splitlines()) - 1), 30)

    def test_v2_helpers_cover_cyrillic_forbidden_terms_and_similarity(self):
        self.assertTrue(has_cyrillic("Текст"))
        self.assertIn("fake ui", contains_forbidden_terms("Avoid fake UI and readable text."))
        self.assertGreaterEqual(similarity_score("camera sees the door", "camera sees the door again"), 80)


if __name__ == "__main__":
    unittest.main()
