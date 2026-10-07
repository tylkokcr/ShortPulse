"""Cutting the user's own clips to a track: the route and the planner."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from app.engines import beat_edit
from tests.test_uploads import FFMPEG, FFPROBE, _client, _FakeQueue, _real_video

pytestmark = pytest.mark.skipif(
    shutil.which(FFPROBE) is None and not Path(FFPROBE).exists(),
    reason=f"{FFPROBE} not available",
)


@pytest.fixture
def beat_app(monkeypatch, tmp_path):
    from fastapi import FastAPI

    from app.api.routes import beat_edits as route
    from app.core import config as core_config
    from app.services import project_store

    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path / "projects")
    monkeypatch.setattr(settings, "ffprobe_binary", FFPROBE)
    project_store.configure(None)

    app = FastAPI()
    app.include_router(route.router)
    app.state.db_pool = None
    queue = _FakeQueue()
    app.state.render_queue = queue
    return app, queue


def _clips(tmp_path: Path, n: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    out = []
    for i in range(n):
        path = _real_video(tmp_path / f"in{i}.mp4", seconds=1.0)
        out.append(("clips", (f"../../evil{i}.mp4", path.read_bytes(), "video/mp4")))
    return out


async def test_clips_and_a_library_track_are_stored_and_queued(beat_app, tmp_path):
    app, queue = beat_app
    from app.api.routes.music import available_tracks

    track = available_tracks()[0].id
    async with _client(app) as client:
        response = await client.post(
            "/api/beat-edits",
            files=_clips(tmp_path, 3),
            data={"music_track_id": track, "style": "calm", "duration_s": "12"},
        )
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["config"]["source"] == "beat_edit"
    assert project["config"]["beat_edit"]["clip_count"] == 3
    assert len(queue.submitted) == 1
    # Stored under fixed names, whatever the client called them.
    stored = sorted(p.name for p in (tmp_path / "projects" / project["config"]["id"] / "source").iterdir())
    assert stored == ["clip_00.mp4", "clip_01.mp4", "clip_02.mp4"]


async def test_a_track_is_required(beat_app, tmp_path):
    app, queue = beat_app
    async with _client(app) as client:
        response = await client.post("/api/beat-edits", files=_clips(tmp_path, 1))
    assert response.status_code == 422
    assert not queue.submitted


async def test_an_unknown_library_track_is_refused(beat_app, tmp_path):
    app, _ = beat_app
    async with _client(app) as client:
        response = await client.post(
            "/api/beat-edits",
            files=_clips(tmp_path, 1),
            data={"music_track_id": "../../etc/passwd"},
        )
    assert response.status_code == 422


async def test_a_clip_that_is_not_video_leaves_nothing_behind(beat_app, tmp_path):
    app, queue = beat_app
    from app.api.routes.music import available_tracks

    files = _clips(tmp_path, 1) + [("clips", ("notes.mp4", b"not a video", "video/mp4"))]
    async with _client(app) as client:
        response = await client.post(
            "/api/beat-edits",
            files=files,
            data={"music_track_id": available_tracks()[0].id},
        )
    assert response.status_code == 422
    assert not queue.submitted
    assert not any((tmp_path / "projects").glob("*/source/*"))


def _grid(tempo: float = 120.0, seconds: float = 60.0, drop: float | None = 20.0) -> beat_edit.BeatGrid:
    period = 60.0 / tempo
    beats = list(np.arange(0.0, seconds, period))
    return beat_edit.BeatGrid(tempo, beats, beats[::4], drop, seconds)


def _motion(name: str, seconds: float = 10.0) -> beat_edit.ClipMotion:
    scores = np.random.default_rng(len(name)).random(int(seconds * 12))
    return beat_edit.ClipMotion(Path(name), seconds, scores)


@pytest.mark.parametrize("style", ["energetic", "cinematic", "calm"])
def test_every_cut_starts_on_a_beat_and_the_drop_starts_one(style):
    grid = _grid()
    plan = beat_edit.plan_edit(grid, [_motion("a"), _motion("bb"), _motion("ccc")], 15.0, style)
    start = plan.music_start
    beats = set(round(b, 3) for b in grid.beats)
    t = start
    starts = []
    for cut in plan.cuts:
        starts.append(round(t, 3))
        t += cut.duration
    assert all(s in beats for s in starts)
    assert round(grid.drop_s, 3) in starts
    assert abs(plan.duration - 15.0) < 0.6


def test_the_same_clip_never_plays_twice_running():
    plan = beat_edit.plan_edit(_grid(), [_motion("a"), _motion("bb")], 15.0, "energetic")
    names = [cut.clip for cut in plan.cuts]
    assert all(a != b for a, b in zip(names, names[1:], strict=False))


def test_a_chosen_start_is_snapped_to_a_beat():
    grid = _grid()
    plan = beat_edit.plan_edit(grid, [_motion("a"), _motion("bb")], 10.0, "calm", music_start=7.3)
    assert round(plan.music_start, 3) in set(round(b, 3) for b in grid.beats)


@pytest.mark.skipif(shutil.which(FFMPEG) is None, reason="needs ffmpeg")
def test_a_steady_click_track_is_read_at_its_tempo(tmp_path):
    click = tmp_path / "click.wav"
    import subprocess

    # A click every half second: 120 BPM.
    subprocess.run(
        [FFMPEG, "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=1000:duration=0.03,apad=pad_dur=0.47,aloop=loop=59:size=22050",
         "-t", "30", str(click)],
        check=True,
    )
    grid = beat_edit.analyze_beats(click, FFMPEG)
    assert abs(grid.tempo_bpm - 120.0) < 3 or abs(grid.tempo_bpm - 60.0) < 2


def _compilation_motion(shot_s: float = 1.2, total_s: float = 18.0) -> beat_edit.ClipMotion:
    """A clip that is itself a compilation: steady motion, a cut every
    `shot_s` seconds."""
    rate = beat_edit._MOTION_FPS
    n = int(total_s * rate)
    cuts = [int(round(k * shot_s * rate)) for k in range(1, int(total_s / shot_s))]
    scores = np.full(n, 6.0)
    return beat_edit.ClipMotion(Path("comp.mp4"), total_s, scores, cuts=cuts, width=1280, height=720)


def test_a_compilation_cut_is_found_and_motion_is_not():
    # Colour make-up change per sample: a pan keeps it roughly steady...
    changes = np.full(200, 0.12) + np.abs(np.sin(np.arange(200))) * 0.08
    changes[50] = 1.4  # ...a cut replaces it
    changes[120] = 1.1
    assert beat_edit._source_cuts(changes) == [51, 121]


def test_a_pan_does_not_read_as_cuts():
    """Every pixel moves in a whip pan, but each region keeps its colours;
    the histogram of a shifted frame is nearly the one it shifted from."""
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, size=(96, 200, 3), dtype=np.uint8)
    frames = np.stack([base[:, i * 3 : i * 3 + 54] for i in range(40)])
    changes = np.abs(np.diff(beat_edit._histograms(frames), axis=0)).sum(axis=1) / 9
    assert beat_edit._source_cuts(changes) == []


@pytest.mark.parametrize("style", ["energetic", "cinematic", "calm"])
def test_no_shot_of_the_edit_contains_a_cut_from_the_source(style):
    clip = _compilation_motion()
    plan = beat_edit.plan_edit(_grid(), [clip], 15.0, style)
    source_cuts = [c / beat_edit._MOTION_FPS for c in clip.cuts]
    for cut in plan.cuts:
        start, end = cut.source_start, cut.source_start + cut.duration * cut.speed
        assert not any(start + 0.05 < c < end - 0.05 for c in source_cuts), (style, start, end)


def test_a_landscape_clip_is_marked_for_the_blurred_frame():
    plan = beat_edit.plan_edit(_grid(), [_compilation_motion()], 10.0, "calm")
    assert all(cut.landscape for cut in plan.cuts)
    graph = beat_edit._segment_filter(plan.cuts[0])
    assert "boxblur" in graph and "overlay" in graph
