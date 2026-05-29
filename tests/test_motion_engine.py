import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from yt_nonstop.render.motion_engine import derive_motion_metadata
from render_project_slideshow_video import build_motion_ffmpeg_command


def test_motion_rules_follow_slot_type_and_visual_function(tmp_path):
    establishing = derive_motion_metadata({"slot_type": "establishing_shot", "visual_function": "set_location"})
    assert establishing["motion_type"] in {"slow_pan", "slow_push_in"}
    assert establishing["motion_intensity"] == "low"

    detail = derive_motion_metadata({"slot_type": "detail_insert", "visual_function": "show_detail"})
    assert detail["motion_type"] == "static_hold"
    assert detail["motion_intensity"] == "none"

    reaction = derive_motion_metadata({"slot_type": "reaction_shot", "visual_function": "show emotion"})
    assert reaction["motion_type"] == "subtle_push_in"

    reveal = derive_motion_metadata({"slot_type": "evidence_insert", "visual_function": "reveal missing interval"})
    assert reveal["motion_type"] in {"static_hold", "slow_push_in"}


def test_motion_marks_film_block_change_as_planned_transition():
    previous = {"film_block_id": "block_a"}
    current = {"film_block_id": "block_b", "slot_type": "establishing_shot"}
    meta = derive_motion_metadata(current, previous)
    assert meta["transition_style"] == "planned_transition"


def test_motion_ffmpeg_command_uses_edl_filtergraph(tmp_path):
    image_a = tmp_path / "a.png"
    image_b = tmp_path / "b.png"
    audio = tmp_path / "audio.mp3"
    output = tmp_path / "out.mp4"
    image_a.write_bytes(b"fake")
    image_b.write_bytes(b"fake")
    audio.write_bytes(b"fake")
    cmd = build_motion_ffmpeg_command(
        edl=[
            {"frame_id": "F0001", "image_path": str(image_a), "duration": 2.0, "motion_type": "slow_push_in", "motion_intensity": "low", "crop_anchor": "center"},
            {"frame_id": "F0002", "image_path": str(image_b), "duration": 1.5, "motion_type": "static_hold", "motion_intensity": "none", "crop_anchor": "center"},
        ],
        audio_path=audio,
        final_video_path=output,
        fps=24,
        width=1280,
        height=720,
        preset="fast",
        crf="20",
    )
    joined = " ".join(cmd)
    assert "-filter_complex" in cmd
    assert "zoompan" in joined
    assert "concat=n=2" in joined
    assert "1280x720" in joined
    assert str(output) in cmd
