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
def test_an_edit_rises_out_of_and_ends_on_black_and_silence(tmp_path):
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

    first = subprocess.run(
        [FFMPEG, "-nostdin", "-v", "error", "-i", str(out), "-frames:v", "1",
         "-vf", "scale=32:18,format=gray", "-f", "rawvideo", "-"],
        capture_output=True,
        check=True,
    ).stdout
    assert first and sum(first) / len(first) < 12, "the first frame is not black"
    head = subprocess.run(
        [FFMPEG, "-nostdin", "-v", "info", "-t", "0.05", "-i", str(out), "-vn",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    start = float(head.split("max_volume:")[1].split("dB")[0])
    assert start < -15, f"the music starts at full volume ({start} dB)"


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


def test_another_try_leans_away_from_the_last_edits_shots():
    rate = beat_edit._MOTION_FPS
    seconds = 300.0
    cuts = [int(t * rate) for t in range(4, 300, 4)]
    scores = np.random.default_rng(5).random(int(seconds * rate)) + 1.0
    clip = beat_edit.ClipMotion(Path("reel.mp4"), seconds, scores, cuts=cuts, width=1920, height=1080)
    grid = _grid(seconds=120.0)
    first = beat_edit.plan_edit(grid, [clip], 20.0, "energetic", seed=1)
    used = [(c.source_start, c.source_start + c.duration * c.speed) for c in first.cuts]
    again = beat_edit.plan_edit(grid, [clip], 20.0, "energetic", seed=2, history={clip.path: used})

    def overlaps(c):
        s, e = c.source_start, c.source_start + c.duration * c.speed
        return any(not (e <= a or s >= b) for a, b in used)

    assert sum(overlaps(c) for c in again.cuts) <= len(again.cuts) // 4


async def test_a_close_up_without_a_face_goes_back_to_the_blurred_frame(monkeypatch):
    from app.core.config import get_settings
    from app.services import reframe, render_manager

    plan = beat_edit.EditPlan(
        0.0,
        3.0,
        [
            beat_edit.Cut(Path("a.mp4"), 1.0, 1.0, landscape=True, close_crop=True, focus_x=0.2),
            beat_edit.Cut(Path("a.mp4"), 5.0, 1.0, landscape=True, close_crop=True, focus_x=0.2),
        ],
    )
    motion = [beat_edit.ClipMotion(Path("a.mp4"), 10.0, np.ones(120), width=1920, height=1080)]
    answers = iter([[], [reframe.Sample(0.0, 0.7), reframe.Sample(0.3, 0.72)]])

    async def track(*args, **kwargs):
        return next(answers)

    monkeypatch.setattr(reframe, "is_available", lambda: True)
    monkeypatch.setattr(reframe, "track_subject", track)
    await render_manager._frame_close_ups_on_faces(plan, motion, get_settings())
    smear, face = plan.cuts
    assert not smear.close_crop and smear.zoom == beat_edit.NEAR_ZOOM
    assert face.close_crop and face.focus_x == 0.72


def test_an_edit_is_remembered_by_its_footage(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services import render_manager

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path / "projects")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x" * 5000)
    copy = tmp_path / "same-footage-other-name.mp4"
    copy.write_bytes(b"x" * 5000)
    plan = beat_edit.EditPlan(0.0, 2.0, [beat_edit.Cut(clip, 3.0, 2.0)])
    render_manager._remember_edit(plan, get_settings())
    assert render_manager._edit_history([copy], get_settings()) == {copy: [(3.0, 5.0)]}


def _source_cut_times(clip):
    return [c / beat_edit._MOTION_FPS for c in clip.cuts]


def test_an_energetic_cut_is_one_whole_shot_of_the_source_and_keeps_its_end():
    """Each cut is a moment from its start to its end. The source was cut
    just after each payoff, so a cut keeps the end of its shot — the one
    before cut early was the shot before the goal."""
    clip = _compilation_motion(shot_s=2.0, total_s=120.0)
    plan = beat_edit.plan_edit(_grid(seconds=120.0), [clip], 20.0, "energetic")
    bounds = [0.0, *_source_cut_times(clip), clip.duration_s]
    for cut in plan.cuts:
        start, end = cut.source_start, cut.source_start + cut.duration * cut.speed
        assert not any(start + 0.05 < c < end - 0.05 for c in bounds), (start, end)
        if not cut.close_crop:
            assert min(abs(end - b) for b in bounds) < 0.15, (start, end)


def test_no_cut_is_a_sliver():
    clip = _compilation_motion(shot_s=2.0, total_s=120.0)
    for style, floor in (("energetic", 1.3), ("cinematic", 2.0), ("calm", 2.5)):
        plan = beat_edit.plan_edit(_grid(seconds=120.0), [clip], 30.0, style, seed=4)
        assert min(c.duration for c in plan.cuts) >= floor, style
        assert abs(plan.duration - 30.0) < 0.6


def test_the_story_opens_and_closes_on_a_reaction_and_the_drop_is_the_strongest_move():
    clip = _two_sizes()
    grid = _grid(drop=20.0)
    plan = beat_edit.plan_edit(grid, [clip], 20.0, "energetic")
    half = clip.duration_s / 2
    t = plan.music_start
    roles = []
    for cut in plan.cuts:
        roles.append(("close" if cut.source_start >= half else "action", round(t, 2), cut.speed))
        t += cut.duration
    assert roles[0][0] == "close" and roles[-1][0] == "close"
    [drop] = [r for r in roles if abs(r[1] - 20.0) < 0.05]
    assert drop[0] == "action" and drop[2] < 1.0


def test_an_action_shot_shows_the_whole_move():
    clip = _compilation_motion(shot_s=2.0, total_s=120.0)
    plan = beat_edit.plan_edit(_grid(seconds=120.0), [clip], 20.0, "energetic")
    actions = [c for c in plan.cuts if not c.close_crop]
    assert actions and all(c.zoom == beat_edit.ACTION_ZOOM and c.ramp is None for c in actions)
    assert "crop=1080:ih:x=" in beat_edit._segment_filter(actions[0])


async def test_an_overlay_title_is_stored_with_its_spaces_collapsed(beat_app, tmp_path):
    app, _ = beat_app
    from app.api.routes.music import available_tracks

    async with _client(app) as client:
        response = await client.post(
            "/api/beat-edits",
            files=_clips(tmp_path, 2),
            data={
                "music_track_id": available_tracks()[0].id,
                "duration_s": "12",
                "overlay_title": "  EN İYİ\n  ÇALIMLAR ",
            },
        )
        too_long = await client.post(
            "/api/beat-edits",
            files=_clips(tmp_path, 2),
            data={"music_track_id": available_tracks()[0].id, "duration_s": "12", "overlay_title": "x" * 61},
        )
    assert response.status_code == 201, response.text
    assert response.json()["config"]["beat_edit"]["overlay_title"] == "EN İYİ ÇALIMLAR"
    assert too_long.status_code == 422


def test_a_title_types_itself_in_word_by_word_on_two_lines(tmp_path):
    path = beat_edit.title_ass("NEYMAR'IN EN İYİ {ÇALIMLARI}", tmp_path / "t.ass", duration=30.0)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    dialogue = next(line for line in text.splitlines() if line.startswith("Dialogue:"))
    # Each word fades in after the one before it.
    assert dialogue.count("\\t(") == 4
    assert "\\t(0,160," in dialogue and "\\t(600,760," in dialogue
    assert "\\N" in dialogue
    # Braces from the user cannot open an override block.
    assert "(ÇALIMLARI)" in dialogue


def test_no_title_without_text_or_room(tmp_path):
    assert beat_edit.title_ass("   ", tmp_path / "a.ass", duration=30.0) is None
    assert beat_edit.title_ass("HELLO", tmp_path / "b.ass", duration=0.3) is None


def test_flat_colour_reads_as_a_graphic_and_grain_does_not():
    rng = np.random.default_rng(1)
    dark_match = rng.normal(30, 4, size=(1, 96, 54)).astype(np.float32)
    end_screen = np.full((1, 96, 54), 20.0, dtype=np.float32)
    end_screen[0, 40:46, 10:44] = 230.0  # a line of text
    assert beat_edit._flatness(dark_match)[0] < 0.3
    assert beat_edit._flatness(end_screen)[0] > beat_edit._FLAT_LEVEL


def test_an_end_screen_never_makes_it_into_an_edit():
    """A compilation ending on "check out these videos": eight seconds where
    nothing moves on flat colour. Scored as the busiest stretch of the clip,
    it is still never cut in."""
    clip = _compilation_motion(shot_s=2.0, total_s=60.0)
    rate = beat_edit._MOTION_FPS
    n = len(clip.scores)
    screen = slice(20 * rate, 28 * rate)
    clip.scores[screen] = 40.0
    clip.activity = np.full(n, 0.1, dtype=np.float32)
    clip.activity[screen] = 0.0
    clip.flat = np.full(n, 0.2, dtype=np.float32)
    clip.flat[screen] = 0.8
    assert clip.graphic(20.0, 22.0) and not clip.graphic(18.0, 20.0)
    for style in ("energetic", "cinematic", "calm"):
        for seed in range(4):
            plan = beat_edit.plan_edit(_grid(seconds=120.0), [clip], 30.0, style, seed=seed)
            for cut in plan.cuts:
                start, end = cut.source_start, cut.source_start + cut.duration * cut.speed
                assert end <= 20.0 + 0.05 or start >= 28.0 - 0.05, (style, seed, start, end)
