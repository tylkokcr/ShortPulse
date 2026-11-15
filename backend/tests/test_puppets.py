"""Puppet shots: the same drawn people in every shot of a story."""

from __future__ import annotations

import shutil

import pytest

from app.engines import puppets
from app.schemas.project import ProjectConfig, ScriptFormat, VideoLength
from app.services import credits

try:
    import cv2  # noqa: F401

    HAVE_CV2 = True
except ImportError:  # the CI image has no OpenCV; the container does
    HAVE_CV2 = False


def test_a_lines_tone_picks_the_face():
    assert puppets.face_for("whispers, scared") == "scared"
    assert puppets.face_for("tense") == "worried"
    assert puppets.face_for("laughs") == "happy"
    assert puppets.face_for(None) == "neutral"


def test_a_puppet_story_costs_less_than_a_drawn_one():
    def price(puppet: bool) -> int:
        return credits.cost_for(
            ProjectConfig(
                topic="x", script_format=ScriptFormat.STORY, video_length=VideoLength.MEDIUM,
                puppet=puppet,
            )
        )

    assert price(True) == 30 and price(True) < price(False)


@pytest.mark.skipif(not HAVE_CV2 or shutil.which("ffmpeg") is None, reason="needs OpenCV and ffmpeg")
def test_a_puppet_shot_is_the_room_with_its_people(tmp_path):
    import numpy as np

    folder = tmp_path / "elif"
    folder.mkdir()
    portrait = np.full((80, 60, 3), (40, 120, 200), np.uint8)
    for pose in puppets.POSES:
        cv2.imwrite(str(folder / f"{pose}.png"), portrait)
    cutout = np.zeros((80, 60, 4), np.uint8)
    cutout[10:70, 10:50, 3] = 255
    cv2.imwrite(str(folder / "cutout.png"), cutout)
    puppet = puppets.load_puppet(folder)
    assert puppet is not None

    plate = tmp_path / "room.png"
    cv2.imwrite(str(plate), np.full((320, 180, 3), 30, np.uint8))
    out = puppets.render_shot(
        tmp_path / "shot.mp4", plate, [("Elif", puppet)], "Elif", "scared", None,
        1.0, 180, 320, 10, "ffmpeg",
    )
    assert out.stat().st_size > 1000
    for framing in ("close", "wide"):
        out = puppets.render_shot(
            tmp_path / f"{framing}.mp4", plate, [("Elif", puppet)], "Elif", None, None,
            1.0, 180, 320, 10, "ffmpeg", 3, framing,
        )
        assert out.stat().st_size > 1000


def test_shot_sizes_cut_in_and_out():
    shots = [
        ([], None, "kitchen"),
        (["Elif"], "narrator", "kitchen"),
        (["Elif", "Can"], "Can", "kitchen"),
        (["Elif", "Can"], "Elif", "kitchen"),
        (["Elif", "Can"], "Can", "kitchen"),
        (["Elif", "Can"], "Elif", "kitchen"),
        (["Elif"], "narrator", "bedroom"),
    ]
    sizes = puppets.plan_framing(shots)
    assert sizes[0] == "wide"
    assert "close" in sizes[2:6]
    assert sizes[-1] == "wide"  # arriving somewhere new
    assert all(not (a == b == c) for a, b, c in zip(sizes, sizes[1:], sizes[2:], strict=False))


def test_night_shots_are_told_from_day_ones():
    from app.engines.visual_engine import shot_is_night

    assert shot_is_night("dark blue bedroom, moonlight on the pillow")
    assert shot_is_night("the kitchen at 3 a.m., one lamp on")
    assert not shot_is_night("a dark wooden table by the nightstand, morning sun")
