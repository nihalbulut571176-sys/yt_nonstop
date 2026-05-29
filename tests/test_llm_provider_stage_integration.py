import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_command_script(path: Path, body: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return f'"{sys.executable}" "{path}"'


def cli_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT / "scripts")] + ([existing] if existing else []))
    if extra:
        env.update(extra)
    return env


def build_project_fixture(tmp_root: Path) -> Path:
    project_root = tmp_root / "project"
    for folder in ["planning", "prompts", "scene_plan", "logs", "qc"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    project = json.loads((ROOT / "deliverables" / "project.template.json").read_text(encoding="utf-8"))
    project["project_id"] = "llm_provider_stage_integration"
    project["meta"]["project_root"] = str(project_root)
    project["meta"]["language"] = "en"
    project_json = project_root / "project.json"
    write_json(project_json, project)
    return project_json


def test_author_visual_allocation_external_uses_command_provider_via_legacy_env_aliases() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp))
        project_root = project_json.parent
        scene_plan_path = project_root / "scene_plan" / "scene_plan.json"
        beats_path = project_root / "planning" / "narration_beats.json"
        output_path = project_root / "planning" / "visual_allocation_plan.json"
        write_json(
            scene_plan_path,
            {
                "scenes": [
                    {
                        "scene_id": "scene_0001",
                        "start": 0.0,
                        "end": 4.0,
                        "duration": 4.0,
                        "voice_text": "An operator enters the boutique.",
                        "camera": "medium shot",
                        "lighting": "warm boutique practicals",
                    }
                ]
            },
        )
        write_json(
            beats_path,
            {
                "beats": [
                    {
                        "beat_id": "beat_0001",
                        "scene_id": "scene_0001",
                        "start": 0.0,
                        "end": 4.0,
                        "duration": 4.0,
                        "voice_text": "An operator enters the boutique.",
                        "spoken_claim": "operator enters the boutique",
                        "must_visualize": ["operator entering a boutique entrance"],
                        "beat_role": "entry_moment",
                        "visual_priority": "high",
                    }
                ]
            },
        )
        command = write_command_script(
            project_root / "visual_provider.py",
            (
                "import json, sys\n"
                "json.load(sys.stdin)\n"
                "sys.stdout.write(json.dumps({'visual_slots':[{'visual_slot_id':'VS0001','beat_ids':['beat_0001'],'scene_ids':['scene_0001'],'source_scene_id':'scene_0001','start':0.0,'end':4.0,'duration':4.0,'slot_type':'character_action','visual_function':'show_spoken_idea','must_show':['operator entering a boutique entrance'],'visualized_claim':'operator enters the boutique','generation_decision':'new_image','shot_design':'character action','priority':'high','variant_count':2,'film_block_id':'boutique_sequence','camera':'medium shot','lighting':'warm boutique practicals','transition_in':'cut','transition_out':'cut_on_phrase_end','reason':'show entry'}]}))\n"
            ),
        )
        env = cli_env(
            {
                "YT_NONSTOP_VISUAL_ALLOCATOR_MODE": "command",
                "YT_NONSTOP_VISUAL_ALLOCATOR_CMD": command,
            }
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "author_visual_allocation_plan.py"),
                "--project-json",
                str(project_json),
                "--provider",
                "external",
            ],
            check=True,
            timeout=30,
            env=env,
        )
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["visual_slots"][0]["visual_slot_id"] == "VS0001"


def test_author_narration_beats_external_uses_command_provider_and_preserves_timing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp))
        project_root = project_json.parent
        beats_path = project_root / "planning" / "narration_beats.json"
        scene_plan_path = project_root / "scene_plan" / "scene_plan.json"
        write_json(
            beats_path,
            {
                "beats": [
                    {
                        "beat_id": "beat_0001",
                        "scene_id": "scene_0001",
                        "start": 1.0,
                        "end": 3.5,
                        "duration": 2.5,
                        "voice_text": "A detective studies the evidence board.",
                    }
                ]
            },
        )
        write_json(
            scene_plan_path,
            {
                "scenes": [
                    {
                        "scene_id": "scene_0001",
                        "start": 1.0,
                        "end": 3.5,
                        "duration": 2.5,
                        "voice_text": "A detective studies the evidence board.",
                        "scene_meaning": "detective studies the evidence board",
                        "visual_goal": "show the evidence board and the detective",
                        "what_is_in_frame": "detective at evidence board",
                        "environment": "dim investigation room",
                    }
                ]
            },
        )
        command = write_command_script(
            project_root / "beat_provider.py",
            (
                "import json, sys\n"
                "json.load(sys.stdin)\n"
                "sys.stdout.write(json.dumps({'beats':[{'beat_id':'beat_0001','scene_id':'scene_0001','spoken_claim':'detective studies the evidence board','must_visualize':['detective beside a wall of pinned evidence photos'],'entity_mentions':['detective_01'],'location_mentions':['investigation_room'],'beat_role':'evidence','visual_priority':'high'}]}))\n"
            ),
        )
        env = cli_env(
            {
                "YT_NONSTOP_LLM_PROVIDER_MODE": "command",
                "YT_NONSTOP_LLM_PROVIDER_COMMAND": command,
            }
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "author_narration_beats.py"),
                "--project-json",
                str(project_json),
                "--provider",
                "external",
            ],
            check=True,
            timeout=30,
            env=env,
        )
        payload = json.loads(beats_path.read_text(encoding="utf-8"))
        beat = payload["beats"][0]
        assert beat["start"] == 1.0
        assert beat["end"] == 3.5
        assert beat["duration"] == 2.5
        assert beat["visual_priority"] == "high"


def test_repair_failed_prompts_external_preserves_immutable_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_json = build_project_fixture(Path(tmp))
        project_root = project_json.parent
        drafts_path = project_root / "prompts" / "llm_prompt_drafts.json"
        failed_path = project_root / "qc" / "failed_prompts.json"
        drafts = [
            {
                "scene_id": "scene_0001",
                "frame_id": "F0001",
                "beat_id": "beat_0001",
                "visual_slot_id": "VS0001",
                "start": 0.0,
                "end": 4.0,
                "duration": 4.0,
                "reference_ids": ["ref_detective_01"],
                "film_block_id": "evidence_room_block",
                "shot_type": "medium shot",
                "final_prompt": "bad prompt",
                "negative_prompt": "text",
                "visual_goal": "show detective at board",
            }
        ]
        write_json(drafts_path, drafts)
        write_json(failed_path, drafts)
        command = write_command_script(
            project_root / "repair_provider.py",
            (
                "import json, sys\n"
                "json.load(sys.stdin)\n"
                "sys.stdout.write(json.dumps({'repaired_prompts':[{'scene_id':'scene_0001','frame_id':'F0001','beat_id':'CHANGED','visual_slot_id':'CHANGED','start':99,'end':100,'duration':1.0,'reference_ids':['wrong_ref'],'film_block_id':'changed','shot_type':'close-up','final_prompt':'repaired cinematic prompt','negative_prompt':'watermark','visual_goal':'stronger repaired visual goal'}]}))\n"
            ),
        )
        env = cli_env(
            {
                "YT_NONSTOP_LLM_PROVIDER_MODE": "command",
                "YT_NONSTOP_LLM_PROVIDER_COMMAND": command,
            }
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "repair_failed_prompts.py"),
                "--project-json",
                str(project_json),
                "--provider",
                "external",
                "--failed-json",
                str(failed_path),
            ],
            check=True,
            timeout=30,
            env=env,
        )
        repaired = json.loads(drafts_path.read_text(encoding="utf-8"))[0]
        assert repaired["beat_id"] == "beat_0001"
        assert repaired["visual_slot_id"] == "VS0001"
        assert repaired["start"] == 0.0
        assert repaired["end"] == 4.0
        assert repaired["duration"] == 4.0
        assert repaired["reference_ids"] == ["ref_detective_01"]
        assert repaired["film_block_id"] == "evidence_room_block"
        assert repaired["shot_type"] == "medium shot"
        assert repaired["final_prompt"] == "repaired cinematic prompt"
