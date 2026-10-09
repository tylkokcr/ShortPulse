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
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.03,apad=pad_dur=0.47,aloop=loop=59:size=22050",
            "-t",
            "30",
            str(click),
        ],
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


def _two_sizes(seconds: float = 120.0) -> beat_edit.ClipMotion:
    """First half a wide shot (little of the frame moves, and not much),
    second half a close-up (much of it, a lot)."""
    rate = beat_edit._MOTION_FPS
    n = int(seconds * rate)
    half = n // 2
    activity = np.concatenate([np.full(half, 0.03), np.full(n - half, 0.25)]).astype(np.float32)
    scores = np.concatenate([np.full(half, 2.0), np.full(n - half, 20.0)])
    return beat_edit.ClipMotion(
        Path("match.mp4"), seconds, scores, cuts=[half], width=1920, height=1080, activity=activity
    )


def test_shot_size_is_read_from_how_much_of_the_frame_moves():
    clip = _two_sizes()
    assert clip.scale_at(10) == "wide"
    assert clip.scale_at(len(clip.scores) - 10) == "close"


def test_the_build_up_is_wide_and_the_drop_is_a_close_up():
    """Raw movement would put the close-up everywhere: it moves ten times
    as much. The wide shot still opens the edit."""
    clip = _two_sizes()
    grid = _grid(drop=20.0)
    plan = beat_edit.plan_edit(grid, [clip], 20.0, "energetic")
    half = clip.duration_s / 2
    t = plan.music_start
    sizes = []
    for cut in plan.cuts:
        sizes.append(("wide" if cut.source_start < half else "close", round(t, 2)))
        t += cut.duration
    before = [s for s, at in sizes if at < 20.0 - 0.01]
    on_drop = [s for s, at in sizes if abs(at - 20.0) < 0.05]
    assert before and all(s == "wide" for s in before)
    assert on_drop == ["close"]


def test_choices_are_spread_across_a_long_clip():
    rate = beat_edit._MOTION_FPS
    seconds = 600.0
    n = int(seconds * rate)
    # The busiest minute is the first; everything else is a little quieter.
    scores = np.full(n, 10.0)
    scores[: 60 * rate] = 12.0
    clip = beat_edit.ClipMotion(Path("long.mp4"), seconds, scores, width=1920, height=1080)
    plan = beat_edit.plan_edit(_grid(seconds=120.0), [clip], 30.0, "cinematic")
    starts = sorted(c.source_start for c in plan.cuts)
    assert starts[-1] - starts[0] > 300, starts


def test_a_shot_keeps_its_payoff_inside_it():
    """A free kick: a still run-up, then the strike. The shot should run
    through the strike, not stop on it or start after it."""
    rate = beat_edit._MOTION_FPS
    n = 20 * rate
    scores = np.full(n, 2.0)
    strike = 10 * rate
    scores[strike : strike + 6] = 30.0  # half a second of everything moving
    clip = beat_edit.ClipMotion(Path("fk.mp4"), 20.0, scores, width=1920, height=1080)
    start = clip.busiest(2.0, [])
    assert start is not None
    position = (strike / rate - start) / 2.0
    assert 0.35 <= position <= 0.85, position


def _setup_then_play(seconds: float = 60.0) -> beat_edit.ClipMotion:
    """A free kick being lined up — wide, and nothing moves — then two
    shots of play a little closer in."""
    rate = beat_edit._MOTION_FPS
    n = int(seconds * rate)
    third = n // 3
    activity = np.full(n, 0.09, dtype=np.float32)
    activity[:third] = 0.002
    scores = np.full(n, 4.0)
    scores[:third] = 1.0
    return beat_edit.ClipMotion(
        Path("wides.mp4"),
        seconds,
        scores,
        cuts=[third, 2 * third],
        width=1920,
        height=1080,
        activity=activity,
    )


def test_a_still_wide_shot_is_not_chosen_for_its_size():
    """The free kick being lined up is the only wide shot, but nothing
    happens in it: the shot of play is taken instead."""
    clip = _setup_then_play()
    start = clip.busiest(2.0, [], prefer=("wide", "medium"))
    assert start is not None and start >= clip.duration_s / 3, start


def test_the_seed_varies_the_shots_and_none_keeps_them():
    clip = _setup_then_play(240.0)
    clip.cuts = [int(k * 4 * beat_edit._MOTION_FPS) for k in range(1, 60)]
    plans = [beat_edit.plan_edit(_grid(), [clip], 15.0, "cinematic", seed=s) for s in range(4)]
    starts = {tuple(round(c.source_start, 2) for c in p.cuts) for p in plans}
    assert len(starts) > 1
    again = [beat_edit.plan_edit(_grid(), [clip], 15.0, "cinematic") for _ in range(2)]
    assert [c.source_start for c in again[0].cuts] == [c.source_start for c in again[1].cuts]


def test_a_wide_landscape_shot_is_shown_closer():
    plan = beat_edit.plan_edit(_grid(), [_two_sizes()], 15.0, "energetic")
    wide = [c for c in plan.cuts if c.source_start < 60.0]
    close = [c for c in plan.cuts if c.source_start >= 60.0]
    assert wide and all(c.zoom == beat_edit.WIDE_ZOOM for c in wide)
    assert close and all(c.zoom == 1.0 for c in close)
    assert "crop=1080:ih:x=" in beat_edit._segment_filter(wide[0])


async def test_a_library_track_can_be_read_before_the_edit(beat_app):
    app, _ = beat_app
    from app.api.routes.music import available_tracks

    track = next(t.id for t in available_tracks() if t.category == "upbeat")
    async with _client(app) as client:
        response = await client.post("/api/beat-edits/analyze", data={"music_track_id": track})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duration_s"] > 10 and 60 < body["tempo_bpm"] < 200
    assert len(body["envelope"]) == 240 and max(body["envelope"]) == 1.0
    assert set(body["suggested_starts"]) == {"10", "15", "30", "60"}
    # A suggested start is on a bar.
    assert round(body["suggested_starts"]["15"], 3) in {round(b, 3) for b in body["downbeats"]}


async def test_an_uploaded_song_is_read_and_not_kept(beat_app, tmp_path):
    app, _ = beat_app
    import subprocess

    song = tmp_path / "song.wav"
    subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=20",
            str(song),
        ],
        check=True,
    )
    async with _client(app) as client:
        response = await client.post(
            "/api/beat-edits/analyze", files={"music": ("song.wav", song.read_bytes(), "audio/wav")}
        )
    assert response.status_code in (200, 422), response.text
    assert not any((tmp_path / "projects").rglob("music.*"))


async def test_analysis_needs_a_song(beat_app):
    app, _ = beat_app
    async with _client(app) as client:
        response = await client.post("/api/beat-edits/analyze")
    assert response.status_code == 422


def test_a_beat_edit_is_priced_by_its_length():
    from app.schemas.project import BeatEditSpec, ProjectConfig, ProjectSource
    from app.services import credits

    def cost(seconds: float | None) -> int:
        spec = BeatEditSpec(clip_count=2, duration_s=seconds) if seconds else None
        return credits.cost_for(ProjectConfig(topic="x", source=ProjectSource.BEAT_EDIT, beat_edit=spec))

    assert cost(10) == cost(15) == 3
    assert cost(30) == 5
    assert cost(60) == 8
    # Stored before lengths were priced: the 15-second price.
    assert cost(None) == 3


@pytest.mark.skipif(shutil.which(FFMPEG) is None, reason="needs ffmpeg")
def test_an_edit_ends_on_black_and_silence(tmp_path):
    import subprocess

    clip = tmp_path / "clip.mp4"
    music = tmp_path / "music.wav"
    subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30:duration=4",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            str(music),
        ],
        check=True,
    )
    plan = beat_edit.EditPlan(
        music_start=0.0,
        duration=3.0,
        cuts=[beat_edit.Cut(clip, 0.0, 1.5, landscape=True), beat_edit.Cut(clip, 2.0, 1.5, landscape=True)],
    )
    out = beat_edit.render_edit(plan, music, tmp_path / "edit.mp4", tmp_path / "work", FFMPEG)

    last = subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-sseof",
            "-0.1",
            "-i",
            str(out),
            "-frames:v",
            "1",
            "-vf",
            "scale=32:18,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert last and sum(last) / len(last) < 12, "the last frame is not black"
    tail = subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "info",
            "-sseof",
            "-0.15",
            "-i",
            str(out),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    peak = float(tail.split("max_volume:")[1].split("dB")[0])
    assert peak < -25, f"the music is still playing at the end ({peak} dB)"


def test_a_ramp_takes_the_source_its_speeds_add_up_to():
    assert abs(beat_edit.ramp_speed(beat_edit.RAMP_HARD) - (0.35 * 1.8 + 0.35 * 0.45 + 0.30 * 1.4)) < 1e-9


@pytest.mark.skipif(shutil.which(FFMPEG) is None, reason="needs ffmpeg")
def test_a_ramped_close_up_fills_the_frame_and_keeps_its_length(tmp_path):
    """Fast, slow, fast — and still exactly the cut's length on the
    timeline, or every cut after it would land off the beat."""
    import subprocess

    clip = tmp_path / "wide.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=6",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    ramp = beat_edit.RAMP_HARD
    cut = beat_edit.Cut(
        clip,
        0.5,
        2.0,
        speed=beat_edit.ramp_speed(ramp),
        effects=["grade"],
        landscape=True,
        close_crop=True,
        focus_x=0.3,
        ramp=ramp,
    )
    out = tmp_path / "cut.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-ss",
            "0.5",
            "-t",
            "3",
            "-i",
            str(clip),
            "-filter_complex",
            beat_edit._segment_filter(cut),
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(out),
        ],
        check=True,
    )
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=width,height,nb_read_frames",
            "-of",
            "csv=p=0",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    width, height, frames = (int(v) for v in probe.split(","))
    assert (width, height) == (beat_edit.WIDTH, beat_edit.HEIGHT)
    assert abs(frames - 2.0 * beat_edit.FPS) <= 1


def test_ramps_go_on_close_ups_not_wide_shots():
    clip = _two_sizes()
    plan = beat_edit.plan_edit(_grid(), [clip], 20.0, "energetic", seed=3)
    half = clip.duration_s / 2
    ramped = [c for c in plan.cuts if c.ramp]
    assert ramped and all(c.source_start >= half for c in ramped)
    assert all(c.close_crop for c in plan.cuts if c.source_start >= half)
    assert not any(c.close_crop for c in plan.cuts if c.source_start < half)
