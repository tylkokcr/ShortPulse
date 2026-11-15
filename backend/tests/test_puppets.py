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

    assert price(True) == 25 and price(True) < price(False)


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
