import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from llm_pipeline_contracts import compute_prompt_hash  # noqa: E402
from yt_nonstop.state.pipeline_state import connect as connect_state_db  # noqa: E402
from yt_nonstop.state.pipeline_state import mark_frame_failed, mark_frame_success, resolve_state_db_path  # noqa: E402
from pipeline_contracts import stable_hash  # noqa: E402


TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082"
)


class PipelineStateTests(unittest.TestCase):
    def build_generation_fixture(self, tmp_root: Path) -> Path:
        project_root = tmp_root / "project"
        for folder in ["exports", "prompts", "scene_plan", "images/run", "logs"]:
            (project_root / folder).mkdir(parents=True, exist_ok=True)

        project = json.loads((ROOT / "deliverables" / "project.template.json").read_text(encoding="utf-8"))
        project["project_id"] = "state_resume_smoke"
        project["meta"]["project_root"] = str(project_root)
        project["current_stage"] = "generate_images"
        project["images"]["run_manifest_path"] = str(project_root / "images" / "run" / "run_manifest.json")
        project["images"]["raw_images_dir"] = str(project_root / "images" / "run" / "images")
        project["prompts"]["fastgen_export_path"] = str(project_root / "exports" / "fastgen_prompts.md")
        project["prompts"]["generator_ready_path"] = str(project_root / "exports" / "fastgen_prompts.md")
        project["prompts"]["prompt_package_path"] = str(project_root / "prompts" / "prompt_package.json")
        project["prompts"]["final_scene_plan_path"] = str(project_root / "scene_plan" / "final_scene_plan.json")
        project["prompts"]["reference_mapping_path"] = str(project_root / "prompts" / "fastgen_ref_paths.json")

        prompt_text = "\n\n".join(
            [
                "No character reference. Premium documentary evidence image one.",
                "No character reference. Premium documentary evidence image two.",
            ]
        ) + "\n"
        prompt_file = project_root / "exports" / "fastgen_prompts.md"
        prompt_file.write_text(prompt_text, encoding="utf-8")
        package_items = [
            {"scene_id": "scene_0001", "frame_id": "F0001", "visual_slot_id": "VS0001", "variant_count": 1},
            {"scene_id": "scene_0002", "frame_id": "F0002", "visual_slot_id": "VS0002", "variant_count": 1},
        ]
        package_signature = stable_hash({"eligible_frames": ["F0001", "F0002"], "items": package_items})
        meta = {
            "package_path": str(project_root / "prompts" / "generation_locked_frames.json"),
            "package_signature": package_signature,
            "prompt_count": 2,
            "package_items": package_items,
        }
        meta["export_signature"] = stable_hash(
            {
                "package_path": meta["package_path"],
                "package_signature": meta["package_signature"],
                "prompt_count": meta["prompt_count"],
                "content": prompt_text,
            }
        )
        (project_root / "exports" / "fastgen_prompts.md.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (project_root / "prompts" / "prompt_package.json").write_text(json.dumps({"items": package_items}), encoding="utf-8")
        (project_root / "scene_plan" / "final_scene_plan.json").write_text(
            json.dumps(
                {
                    "scenes": [
                        {"scene_id": "scene_0001", "frame_id": "F0001", "notes": []},
                        {"scene_id": "scene_0002", "frame_id": "F0002", "notes": []},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (project_root / "prompts" / "fastgen_ref_paths.json").write_text("{}", encoding="utf-8")

        project_json = project_root / "project.json"
        project_json.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        return project_json

    def test_resume_skips_successful_frames_without_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.build_generation_fixture(Path(tmp))
            project_root = project_json.parent
            images_dir = project_root / "images" / "run" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            prompt_settings = {"provider": "fastgen_openai_v4", "size": "1024x1024", "aspect_ratio": "16:9"}
            prompts = [
                "Premium documentary evidence image one.",
                "Premium documentary evidence image two.",
            ]
            state_db = resolve_state_db_path(project_json, json.loads(project_json.read_text(encoding="utf-8")))
            conn = connect_state_db(state_db)
            try:
                for index, frame_id in enumerate(["F0001", "F0002"], start=1):
                    image_path = images_dir / f"scene_{index:04d}_V01.png"
                    image_path.write_bytes(TINY_PNG)
                    mark_frame_success(
                        conn,
                        project_id="state_resume_smoke",
                        frame_id=frame_id,
                        visual_slot_id=f"VS{index:04d}",
                        prompt_hash=compute_prompt_hash(prompt=prompts[index - 1], refs=[], settings=prompt_settings),
                        image_path=str(image_path),
                    )
            finally:
                conn.close()

            env = os.environ.copy()
            env.pop("FAST_GEN_API_KEY", None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_project_fastgen_generation.py"),
                    "--project-json",
                    str(project_json),
                    "--resume",
                    "--retry-rounds",
                    "1",
                ],
                check=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertIn("run_manifest.json", result.stdout)
            manifest = json.loads((project_root / "images" / "run" / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["completed_count"], 2)
            self.assertEqual(manifest["failed_count"], 0)
            self.assertEqual(manifest["missing_count"], 0)

    def test_generator_accepts_pilot_resume_args_and_skips_without_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.build_generation_fixture(Path(tmp))
            project_root = project_json.parent
            images_dir = project_root / "images" / "run" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            prompt_settings = {"provider": "fastgen_openai_v4", "size": "1024x1024", "aspect_ratio": "16:9"}
            image_path = images_dir / "scene_0001_V01.png"
            image_path.write_bytes(TINY_PNG)
            state_db = resolve_state_db_path(project_json, json.loads(project_json.read_text(encoding="utf-8")))
            conn = connect_state_db(state_db)
            try:
                mark_frame_success(
                    conn,
                    project_id="state_resume_smoke",
                    frame_id="F0001",
                    visual_slot_id="VS0001",
                    prompt_hash=compute_prompt_hash(
                        prompt="Premium documentary evidence image one.",
                        refs=[],
                        settings=prompt_settings,
                    ),
                    image_path=str(image_path),
                )
            finally:
                conn.close()

            env = os.environ.copy()
            env.pop("FAST_GEN_API_KEY", None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "fastgen_openai_v4_generate.py"),
                    "--prompts",
                    str(project_root / "exports" / "fastgen_prompts.md"),
                    "--refs",
                    str(project_root / "prompts" / "fastgen_ref_paths.json"),
                    "--workdir",
                    str(project_root / "images" / "run"),
                    "--size",
                    "1024x1024",
                    "--aspect-ratio",
                    "16:9",
                    "--project-id",
                    "state_resume_smoke",
                    "--state-db",
                    str(state_db),
                    "--state-stage",
                    "generate_images",
                    "--resume",
                    "--frame-id",
                    "F0001",
                ],
                check=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(payload["done"], 0)
            self.assertEqual(payload["skipped"], 1)
            self.assertEqual(payload["failed"], 0)
            self.assertEqual(payload["filtered"], 1)

    def test_project_status_reports_failed_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_json = self.build_generation_fixture(Path(tmp))
            project = json.loads(project_json.read_text(encoding="utf-8"))
            state_db = resolve_state_db_path(project_json, project)
            conn = connect_state_db(state_db)
            try:
                mark_frame_failed(
                    conn,
                    project_id="state_resume_smoke",
                    frame_id="F0002",
                    visual_slot_id="VS0002",
                    prompt_hash="hash-2",
                    error_message="synthetic failure",
                )
            finally:
                conn.close()
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "project_status.py"),
                    "--project-json",
                    str(project_json),
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["by_status"], {"failed": 1})
            self.assertEqual(payload["failed_frames"][0]["frame_id"], "F0002")


if __name__ == "__main__":
    unittest.main()
