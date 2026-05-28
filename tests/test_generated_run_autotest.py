import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from autotest_generated_run import run_autotest  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


@unittest.skipIf(Image is None, "Pillow not installed")
class GeneratedRunAutotestTests(unittest.TestCase):
    def test_autotest_flags_missing_refs_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            report_dir = project_root / "reports"
            prompts_dir = project_root / "prompts"
            images_dir = project_root / "images" / "fastgen_run_test" / "images"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            images_dir.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)

            project_json = project_root / "project.json"
            final_scene_plan_path = prompts_dir / "final_scene_plan.json"
            subject_registry_path = prompts_dir / "subject_registry.json"
            export_path = project_root / "exports" / "fastgen_prompts.md"
            export_path.parent.mkdir(parents=True, exist_ok=True)

            final_scene_plan_path.write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene_0001",
                                "voice_text": "Two people enter the boutique.",
                                "mini_world": "entry choreography",
                                "why_this_frame_exists": "Show the operation beginning.",
                                "director_prompt": {"visual_intent": "two calm entrants crossing the boutique threshold", "scene_meaning": "the operation begins"},
                                "image_prompt_final": "documentary image of two calm entrants crossing the boutique threshold",
                            },
                            {
                                "scene_id": "scene_0002",
                                "voice_text": "A guard remains near the glass barrier.",
                                "mini_world": "guarded showroom perimeter",
                                "why_this_frame_exists": "Show security presence.",
                                "director_prompt": {"visual_intent": "guarded glass barrier and protected display zone", "scene_meaning": "security presence"},
                                "image_prompt_final": "documentary image of guarded glass barrier and protected display zone",
                            },
                            {
                                "scene_id": "scene_0003",
                                "voice_text": "The timing advantage becomes obvious.",
                                "mini_world": "investigative contrast",
                                "why_this_frame_exists": "Turn the narration into a distinct pattern_break image with a fresh investigative purpose.",
                                "director_prompt": {"visual_intent": "unexpected visual turn that interrupts repetition", "scene_meaning": "timing advantage"},
                                "image_prompt_final": "Premium cinematic documentary still, 16:9. unexpected visual turn that interrupts repetition, inside investigative contrast, visual function pattern_break. Frame purpose: Turn the narration into a distinct pattern_break image with a fresh investigative purpose.. Realistic textures, investigative realism, no lettering, silent documentary image, no speaking characters.",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            subject_registry_path.write_text(
                json.dumps(
                    {
                        "subjects": [
                            {"subject_id": "lead_operator", "reference_asset_ids": ["ref_lead_operator_identity_sheet"]},
                            {"subject_id": "support_operator", "reference_asset_ids": ["ref_support_operator_identity_sheet"]},
                            {"subject_id": "security_guard", "reference_asset_ids": ["ref_security_guard_identity_sheet"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            export_path.write_text(
                "\n\n".join(
                    [
                        "No character reference. documentary image of two calm entrants crossing the boutique threshold",
                        "Use reference image: ref_security_guard_identity_sheet. documentary image of guarded glass barrier and protected display zone",
                        "No character reference. Premium cinematic documentary still, 16:9. unexpected visual turn that interrupts repetition, inside investigative contrast, visual function pattern_break. Frame purpose: Turn the narration into a distinct pattern_break image with a fresh investigative purpose.. Realistic textures, investigative realism, no lettering, silent documentary image, no speaking characters.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            for scene_id in ("scene_0001", "scene_0002", "scene_0003"):
                image = Image.new("RGB", (1792, 1024), color=(120, 120, 120))
                image.save(images_dir / f"{scene_id}_V01.png")

            project_json.write_text(
                json.dumps(
                    {
                        "project_id": "autotest_fixture",
                        "meta": {"project_root": str(project_root)},
                        "prompts": {
                            "final_scene_plan_path": str(final_scene_plan_path),
                            "subject_registry_path": str(subject_registry_path),
                            "fastgen_export_path": str(export_path),
                        },
                        "qc": {},
                    }
                ),
                encoding="utf-8",
            )

            json_path, _csv_path, _md_path = run_autotest(project_json, project_root / "images" / "fastgen_run_test")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            by_scene = {row["scene_id"]: row for row in payload["frames"]}
            self.assertIn("missing_reference_for_human_frame", by_scene["scene_0001"]["flags"])
            self.assertIn("possible_duplicate_image", by_scene["scene_0002"]["flags"])
            self.assertEqual(by_scene["scene_0003"]["semantic_status"], "fail")
            self.assertIn("conceptual_core_not_filmable", by_scene["scene_0003"]["flags"])
            self.assertIn("severe_pipeline_meta_language", by_scene["scene_0003"]["flags"])


if __name__ == "__main__":
    unittest.main()
