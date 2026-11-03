"""Maps are drawn from real outlines, for scenes the script marks as maps."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.engines import maps
from app.engines.script_engine import _scene_map


def test_countries_resolve_by_code_or_any_stored_name():
    assert maps.find_country("TUR") == "TUR"
    assert maps.find_country("Türkiye") == "TUR"
    assert maps.find_country("Polonya") == maps.find_country("Poland") == "POL"
    assert maps.find_country("Atlantis") is None


def test_the_scripts_map_is_resolved_and_cleaned():
    spec = _scene_map(
        {
            "focus": "Japan",
            "action": "MARK",
            "places": [
                {"name": "Tokyo", "lat": 35.68, "lon": 139.69},
                {"name": "Nowhere", "lat": "north", "lon": 0},
                {"name": "", "lat": 1, "lon": 1},
            ],
        }
    )
    assert spec is not None and spec.focus == ["JPN"] and spec.action == "mark"
    assert [p.name for p in spec.places] == ["Tokyo"]
    assert _scene_map({"focus": ["Atlantis"]}) is None
    assert _scene_map({"focus": "France", "action": "explode"}).action == "glow"
    assert _scene_map("a map of France") is None


@pytest.mark.skipif(not maps.available(), reason="needs OpenCV")
def test_a_vanish_shot_goes_dark_where_the_country_was():
    import numpy as np

    shot = maps.MapShot(focus=["POL"], action="vanish")
    frames = list(maps.frames(shot, 180, 320, 10, 30))
    assert len(frames) == 30 and frames[0].shape == (320, 180, 3)
    centre = (slice(140, 180), slice(70, 110))
    # Lit gold at the start, dark at the end.
    assert frames[0][centre].mean() > frames[-1][centre].mean() + 20
    assert np.abs(frames[-1].astype(int) - frames[-2].astype(int)).mean() < 3


@pytest.mark.skipif(
    not maps.available() or shutil.which("ffmpeg") is None, reason="needs OpenCV and ffmpeg"
)
def test_a_shot_renders_to_a_clip(tmp_path: Path):
    out = maps.render_clip(maps.MapShot(focus=["TUR"]), tmp_path / "m.mp4", 180, 320, 10, 1.0)
    assert out.stat().st_size > 1000
