import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fastgen_openai_v4_generate import parse_prompt_blocks, validate_prompt_export  # noqa: E402
from prompt_continuity import (  # noqa: E402
    build_continuity_bundle,
    build_scene_prompt,
    extract_scene_semantics,
    run_prompt_package_qa,
    stable_hash,
)


class PromptPipelineTests(unittest.TestCase):
    def make_scene(self, shot_index: int, voice_text: str, parts_total: int = 1, part_index: int = 1) -> dict:
        return {
            "scene_id": f"scene_{shot_index:04d}",
            "shot_index": shot_index,
            "source_segment_id": shot_index,
            "source_index": shot_index,
            "part_index": part_index,
            "parts_total": parts_total,
            "start": float(shot_index),
            "end": float(shot_index) + 1.0,
            "duration": 1.0,
            "voice_text": voice_text,
        }

    def make_project(self) -> dict:
        return {
            "project_id": "pink_panthers_test",
            "meta": {"title": "Pink Panthers Test"},
            "rewrite": {},
            "inputs": {},
            "prompts": {"prompt_language": "English", "style_preset": "cinematic-realistic-v1"},
        }

    def test_assault_semantics_stay_specific(self):
        scene = self.make_scene(14, "Сотрудницу ослепляют раздражающим газом.", parts_total=2, part_index=1)
        descriptor = extract_scene_semantics(scene, "luxury_jewel_heist_documentary")
        self.assertEqual(descriptor["event_type"], "assault")
        self.assertTrue(descriptor["event_clarity_required"])
        self.assertEqual(descriptor["part_semantic_role"], "moment")

    def test_reaction_escape_does_not_fall_into_bridge(self):
        scenes = [
            self.make_scene(15, "И пока люди вокруг еще пытаются понять, что случилось, преступники уже уходят. Это не сцена из фильма.", 2, 1),
            self.make_scene(16, "И пока люди вокруг еще пытаются понять, что случилось, преступники уже уходят. Это не сцена из фильма.", 2, 2),
        ]
        bundle = build_continuity_bundle(self.make_project(), scenes, "Pink Panthers")
        roles = [bundle["shot_role_map"][scene["scene_id"]] for scene in scenes]
        self.assertEqual(roles[0], "delayed_reaction")
        self.assertEqual(roles[1], "operator_exit")

    def test_historical_context_role(self):
        scene = self.make_scene(17, "Это Токио, 2004 год.")
        bundle = build_continuity_bundle(self.make_project(), [scene], "Pink Panthers")
        self.assertEqual(bundle["shot_role_map"][scene["scene_id"]], "historical_context")

    def test_network_and_mechanism_are_not_bridge(self):
        scene = self.make_scene(
            28,
            "Это была сеть выходцев с Балкан, бывших военных, водителей, разведчиков и специалистов по логистике.",
            parts_total=2,
            part_index=1,
        )
        descriptor = extract_scene_semantics(scene, "luxury_jewel_heist_documentary")
        self.assertEqual(descriptor["event_type"], "network_scale")

    def test_prompt_qa_fails_for_generic_subjects(self):
        items = [
            {
                "scene_id": "scene_0001",
                "shot_role": "investigative_bridge",
                "primary_subject": "the recurring documentary subject",
                "environment": "same",
                "scale": "medium",
                "angle": "medium",
                "lighting_family": "neutral",
                "density": "clean",
                "visual_function": "transition",
                "key_beat": False,
                "variant_count": 1,
                "active_entity_ids": [],
                "continuity_cast": [],
                "prompt": "Scene meaning: x",
                "semantic_descriptor": {
                    "event_clarity_required": False,
                },
            }
        ]
        qa = run_prompt_package_qa(items, "luxury_jewel_heist_documentary")
        self.assertEqual(qa["status"], "failed")

    def test_build_scene_prompt_uses_concrete_subject(self):
        scene = self.make_scene(21, "Их прозвали Розовыми пантерами.")
        bundle = build_continuity_bundle(self.make_project(), [scene], "Pink Panthers")
        authored = build_scene_prompt(scene, bundle)
        self.assertNotEqual(authored["primary_subject"], "the recurring documentary subject")
        self.assertEqual(authored["shot_role"], "identity_reveal")
        self.assertEqual(authored["prompt_sections"][0], "Scene meaning:")
        self.assertEqual(authored["beat_priority"], "hero")

    def test_prompt_export_validation_detects_stale_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "fastgen_prompts.md"
            prompt_text = "No character reference. prompt one\n\nNo character reference. prompt two\n"
            prompt_path.write_text(prompt_text, encoding="utf-8")
            blocks = parse_prompt_blocks(prompt_path)
            meta_path = prompt_path.with_suffix(prompt_path.suffix + ".meta.json")
            bad_meta = {
                "package_path": "fake.json",
                "package_signature": "abc",
                "prompt_count": 2,
                "export_signature": stable_hash({"package_path": "fake.json", "package_signature": "wrong", "prompt_count": 2, "content": prompt_text}),
            }
            meta_path.write_text(json.dumps(bad_meta), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                validate_prompt_export(prompt_path, blocks)

    def test_opening_security_beat_becomes_key_beat(self):
        scene = self.make_scene(1, "Бутик, камеры и охрана делают пространство почти стерильным.")
        descriptor = extract_scene_semantics(scene, "luxury_jewel_heist_documentary")
        self.assertTrue(descriptor["key_beat"])
        self.assertIn(descriptor["beat_priority"], {"hero", "priority"})

    def test_prompt_qa_requires_diversity_and_sections(self):
        items = [
            {
                "scene_id": "scene_0001",
                "shot_role": "luxury_establishing",
                "primary_subject": "protected boutique interior",
                "environment": "tokyo boutique",
                "scale": "wide",
                "angle": "wide architectural documentary angle",
                "lighting_family": "warm",
                "density": "layered",
                "visual_function": "hook",
                "key_beat": False,
                "variant_count": 1,
                "active_entity_ids": [],
                "continuity_cast": [],
                "prompt": "\n".join(
                    [
                        "Scene meaning: x",
                        "Visual intent: x",
                        "Main subject: x",
                        "Environment storytelling: x",
                        "Composition: x",
                        "Camera: x",
                        "Lighting: x",
                        "Mood: x",
                        "Important details:",
                        "Restrictions: x",
                    ]
                ),
                "semantic_descriptor": {
                    "event_clarity_required": False,
                },
            },
            {
                "scene_id": "scene_0002",
                "shot_role": "luxury_establishing",
                "primary_subject": "protected boutique interior",
                "environment": "tokyo boutique",
                "scale": "wide",
                "angle": "wide architectural documentary angle",
                "lighting_family": "warm",
                "density": "layered",
                "visual_function": "hook",
                "key_beat": False,
                "variant_count": 1,
                "active_entity_ids": [],
                "continuity_cast": [],
                "prompt": "Scene meaning: incomplete",
                "semantic_descriptor": {
                    "event_clarity_required": False,
                },
            },
        ]
        qa = run_prompt_package_qa(items, "luxury_jewel_heist_documentary")
        self.assertEqual(qa["status"], "failed")
        self.assertTrue(any("adjacent-shot diversity too low" in issue for issue in qa["issues"]))
        self.assertTrue(any("prompt missing section" in issue for issue in qa["issues"]))


if __name__ == "__main__":
    unittest.main()
