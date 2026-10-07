"""Cut a set of clips to the beat of a track, with the effects fan edits use.

Prototype. Everything here works on files the caller already has — the
user's own clips and a track they supplied or picked from the licensed
library. Nothing is searched for or downloaded: footage of someone else's
broadcast is not ours to cut, and a tool that went and fetched it would
make the infringement ours rather than the uploader's.

Four steps, each a plain function so they can be looked at on their own:

* `analyze_beats` — tempo, beat times, bar starts and the drop, from the
  audio alone (numpy; no librosa, which would be a large dependency for
  one onset envelope).
* `motion_profile` — how much each clip moves, frame by frame, so a cut
  takes the busiest stretch rather than whatever happens to be first.
* `plan_edit` — which clip and which stretch of it sits on each beat, and
  which effect hits where.
* `render_edit` — ffmpeg, one short segment per cut, then joined and laid
  over the track.
"""

from __future__ import annotations

import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 22050
_HOP = 512
_FRAME = 2048

WIDTH, HEIGHT, FPS = 1080, 1920, 30


# ---------------------------------------------------------------------------
# Beats
# ---------------------------------------------------------------------------


@dataclass
class BeatGrid:
    tempo_bpm: float
    beats: list[float]  # seconds
    downbeats: list[float]  # first beat of each bar
    drop_s: float | None  # where the energy jumps, if anywhere
    duration_s: float


def _decode_mono(path: Path, ffmpeg: str = "ffmpeg") -> np.ndarray:
    raw = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-ac", "1",
         "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


def _onset_envelope(signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Spectral flux, and RMS per hop: where new sound starts, and how loud."""
    n_frames = 1 + max(0, (len(signal) - _FRAME) // _HOP)
    window = np.hanning(_FRAME).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(signal, _FRAME)[::_HOP][:n_frames]
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
    log_spec = np.log1p(spectrum * 10)
    flux = np.maximum(0.0, np.diff(log_spec, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # Remove the slow trend so a loud section does not count as one long onset.
    kernel = np.ones(16) / 16
    flux = np.maximum(0.0, flux - np.convolve(flux, kernel, mode="same"))
    flux /= flux.max() or 1.0
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return flux, rms


def _estimate_period(onset: np.ndarray, fps: float) -> float:
    """Beat period in envelope frames, by autocorrelation, leaning to ~120 BPM."""
    centered = onset - onset.mean()
    corr = np.correlate(centered, centered, mode="full")[len(centered) - 1 :]
    best_lag, best_score = None, -math.inf
    for bpm in np.arange(70.0, 181.0, 0.5):
        lag = 60.0 * fps / bpm
        lo, hi = int(math.floor(lag)), int(math.ceil(lag))
        if hi >= len(corr):
            continue
        value = corr[lo] + (corr[hi] - corr[lo]) * (lag - lo)
        # Mild preference for the range most music is felt in, so a track
        # at 70 does not get read as 140 or the other way round at random.
        weight = math.exp(-0.5 * (math.log2(bpm / 120.0) / 0.9) ** 2)
        if value * weight > best_score:
            best_lag, best_score = lag, value * weight
    return float(best_lag or 60.0 * fps / 120.0)


def _track_beats(onset: np.ndarray, period: float, tightness: float = 100.0) -> list[int]:
    """Dynamic-programming beat tracker (Ellis 2007): beats land on onsets
    while staying close to the tempo."""
    n = len(onset)
    score = onset.astype(np.float64).copy()
    back = np.full(n, -1)
    lo_off, hi_off = int(round(period / 2)), int(round(period * 2))
    for t in range(n):
        lo, hi = t - hi_off, t - lo_off
        if hi <= 0:
            continue
        lo = max(lo, 0)
        prev = np.arange(lo, hi)
        penalty = -tightness * (np.log((t - prev) / period)) ** 2
        candidates = score[prev] + penalty
        k = int(np.argmax(candidates))
        score[t] = onset[t] + candidates[k]
        back[t] = prev[k]
    # Start from the best-scoring frame in the last period and walk back.
    tail = max(0, n - int(period))
    t = tail + int(np.argmax(score[tail:]))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    return beats[::-1]


def analyze_beats(audio: Path, ffmpeg: str = "ffmpeg") -> BeatGrid:
    signal = _decode_mono(audio, ffmpeg)
    onset, rms = _onset_envelope(signal)
    fps = SAMPLE_RATE / _HOP
    period = _estimate_period(onset, fps)
    frames = _track_beats(onset, period)
    beats = [f / fps for f in frames]

    # Bars: of the four ways to group beats in fours, the one whose first
    # beats carry the most onset strength.
    phase = max(range(4), key=lambda p: sum(onset[f] for f in frames[p::4]))
    downbeats = beats[phase::4]

    # The drop: the bar where the next four bars are loudest relative to
    # the four before, outside the very start and end.
    bar_rms = [float(rms[frames[i] : frames[min(i + 4, len(frames) - 1)]].mean() or 0)
               for i in range(phase, len(frames) - 4, 4)]
    drop = None
    if len(bar_rms) >= 6:
        best, best_ratio = None, 1.15
        for i in range(2, len(bar_rms) - 2):
            before = np.mean(bar_rms[max(0, i - 2) : i]) + 1e-6
            after = np.mean(bar_rms[i : i + 2])
            ratio = after / before
            if ratio > best_ratio:
                best, best_ratio = i, ratio
        if best is not None:
            drop = downbeats[best]

    return BeatGrid(
        tempo_bpm=60.0 * fps / period,
        beats=beats,
        downbeats=downbeats,
        drop_s=drop,
        duration_s=len(signal) / SAMPLE_RATE,
    )


# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------

_MOTION_FPS = 12
_MOTION_W, _MOTION_H = 54, 96


@dataclass
class ClipMotion:
    path: Path
    duration_s: float
    scores: np.ndarray  # mean absolute frame difference, per sample

    def busiest(self, length_s: float, avoid: list[tuple[float, float]]) -> float:
        """Start of the most active `length_s` stretch not overlapping `avoid`."""
        n = max(1, int(round(length_s * _MOTION_FPS)))
        if len(self.scores) <= n:
            return 0.0
        sums = np.convolve(self.scores, np.ones(n), mode="valid")
        order = np.argsort(sums)[::-1]
        for index in order:
            start = index / _MOTION_FPS
            end = start + length_s
            if end > self.duration_s - 0.05:
                continue
            if all(end <= a or start >= b for a, b in avoid):
                return float(start)
        return float(order[0] / _MOTION_FPS)


def motion_profile(clip: Path, ffmpeg: str = "ffmpeg") -> ClipMotion:
    raw = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-i", str(clip), "-vf",
         f"fps={_MOTION_FPS},scale={_MOTION_W}:{_MOTION_H},format=gray",
         "-f", "rawvideo", "-"],
        check=True, capture_output=True,
    ).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, _MOTION_H, _MOTION_W).astype(np.float32)
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2)) if len(frames) > 1 else np.zeros(1)
    scores = np.concatenate([[diffs[0] if len(diffs) else 0.0], diffs])
    return ClipMotion(path=clip, duration_s=len(frames) / _MOTION_FPS, scores=scores)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


@dataclass
class Cut:
    clip: Path
    source_start: float
    duration: float  # on the timeline
    speed: float = 1.0  # < 1 is slow motion
    effects: list[str] = field(default_factory=list)


@dataclass
class EditPlan:
    music_start: float
    duration: float
    cuts: list[Cut]


@dataclass(frozen=True)
class Style:
    """How hard an edit hits, as numbers the planner and renderer read."""

    beats_before_drop: int  # beats per cut in the build-up
    beats_after_drop: int  # beats per cut once it has dropped
    bar_effect: str  # on the first beat of a bar
    drop_effects: tuple[str, ...]
    drop_speed: float
    after_drop_extra: str | None  # every third cut after the drop
    grade: str


STYLES: dict[str, Style] = {
    "energetic": Style(2, 1, "punch", ("flash", "rgbsplit", "shake"), 0.5, "shake", "grade"),
    "cinematic": Style(4, 2, "drift", ("softflash",), 0.5, None, "grade_film"),
    "calm": Style(4, 4, "drift", (), 1.0, None, "grade_soft"),
}


def plan_edit(
    grid: BeatGrid,
    clips: list[ClipMotion],
    target_s: float = 16.0,
    style: str = "energetic",
    music_start: float | None = None,
) -> EditPlan:
    """Which clip, which stretch and which effect sits on each beat.

    Built around the drop: a build-up cut every few beats, then the drop
    with the style's heaviest effect and a slow-motion hit, then cuts on
    the beat to the end. `music_start` overrides where in the track the
    edit begins; by default the drop lands about a third of the way in.
    """
    look = STYLES.get(style, STYLES["energetic"])
    beats = grid.beats
    if len(beats) < 8:
        raise ValueError("Not enough beats were found in that track to cut to.")
    target_s = min(target_s, max(4.0, grid.duration_s - 0.5))

    if music_start is not None:
        # Snap to the nearest beat so the first cut is on one.
        asked = music_start
        music_start = min(beats, key=lambda b: abs(b - asked))
        music_start = min(music_start, max(0.0, grid.duration_s - target_s))
    elif grid.drop_s is not None:
        wanted = grid.drop_s - target_s * 0.33
        starts = [b for b in grid.downbeats if b <= wanted] or grid.downbeats[:1]
        music_start = starts[-1]
    else:
        music_start = grid.downbeats[0]
    music_end = min(music_start + target_s, grid.duration_s)

    timeline = [b for b in beats if music_start - 0.01 <= b <= music_end]
    if not timeline or timeline[-1] < music_end - 0.05:
        timeline.append(music_end)
    downbeats = set(round(d, 3) for d in grid.downbeats)
    drop = grid.drop_s if grid.drop_s is not None and music_start < grid.drop_s < music_end else None

    # At a fast tempo a cut on every beat is too fast to read.
    period = 60.0 / grid.tempo_bpm
    after_step = look.beats_after_drop * (1 if period >= 0.42 else 2)
    before_step = look.beats_before_drop
    points: list[float] = []
    i = 0
    while i < len(timeline) - 1:
        points.append(timeline[i])
        after_drop = drop is not None and timeline[i] >= drop - 0.01
        nxt = i + (after_step if after_drop else before_step)
        # Never step over the drop: the drop always starts a cut.
        if drop is not None and not after_drop:
            drop_index = next((j for j, b in enumerate(timeline) if b >= drop - 0.01), None)
            if drop_index is not None and i < drop_index < nxt:
                nxt = drop_index
        i = nxt
    points.append(timeline[-1])

    used: dict[Path, list[tuple[float, float]]] = {c.path: [] for c in clips}
    order = sorted(clips, key=lambda c: -float(c.scores.mean()))
    cuts: list[Cut] = []
    last: Path | None = None
    turn = 0
    for k in range(len(points) - 1):
        start, end = points[k], points[k + 1]
        length = end - start
        if length < 0.08:
            continue
        effects: list[str] = [look.grade]
        speed = 1.0
        is_drop = drop is not None and abs(start - drop) < 0.05
        if is_drop:
            effects += list(look.drop_effects)
            speed = look.drop_speed
        elif round(start, 3) in downbeats:
            effects.append(look.bar_effect)
        elif look.after_drop_extra and drop is not None and start > drop and k % 3 == 0:
            effects.append(look.after_drop_extra)
        else:
            effects.append("drift")

        # Every clip in turn, busiest first, never the same one twice running.
        clip = order[turn % len(order)]
        if clip.path == last and len(order) > 1:
            turn += 1
            clip = order[turn % len(order)]
        turn += 1
        source_len = length * speed
        if clip.duration_s < source_len + 0.1:
            # A clip shorter than the cut plays at the speed that fits it.
            speed = max(0.25, (clip.duration_s - 0.1) / length)
            source_len = length * speed
        src = clip.busiest(source_len, used[clip.path])
        used[clip.path].append((src, src + source_len))
        cuts.append(Cut(clip=clip.path, source_start=src, duration=length, speed=speed, effects=effects))
        last = clip.path

    return EditPlan(music_start=music_start, duration=points[-1] - points[0], cuts=cuts)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _segment_filter(cut: Cut) -> str:
    """The filter graph for one cut, its clock starting at zero."""
    cover = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1"
    )
    chain = [f"setpts={1 / cut.speed:.4f}*(PTS-STARTPTS)", f"fps={FPS}", cover]
    frames = max(1, int(round(cut.duration * FPS)))

    if "punch" in cut.effects or "flash" in cut.effects or "softflash" in cut.effects:
        # Hit hard and settle: 18% in, back to framing in a quarter second.
        chain.append(
            f"zoompan=z='1+0.18*exp(-on/3.2)':d=1:x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
    elif "drift" in cut.effects:
        chain.append(
            f"zoompan=z='1.0+0.05*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
    if "shake" in cut.effects:
        chain.append(f"scale={int(WIDTH * 1.08)}:{int(HEIGHT * 1.08)}")
        chain.append(
            f"crop={WIDTH}:{HEIGHT}:"
            f"x='(iw-{WIDTH})/2+26*sin(t*55)*exp(-t*5)':"
            f"y='(ih-{HEIGHT})/2+26*cos(t*47)*exp(-t*5)'"
        )
    if "rgbsplit" in cut.effects:
        chain.append("rgbashift=rh=-14:bh=14:enable='lt(t,0.25)'")
    if "grade" in cut.effects:
        chain.append("eq=contrast=1.12:saturation=1.28:gamma=0.97")
        chain.append("vignette=PI/5")
        chain.append("unsharp=5:5:0.6")
    elif "grade_film" in cut.effects:
        # Teal shadows, warm highlights, a little crushed: the trailer look.
        chain.append("colorbalance=rs=-0.06:bs=0.08:rh=0.07:bh=-0.06")
        chain.append("eq=contrast=1.15:saturation=1.05:gamma=0.95")
        chain.append("vignette=PI/4")
    elif "grade_soft" in cut.effects:
        chain.append("eq=contrast=1.04:saturation=1.08:brightness=0.02")
    graph = ",".join(chain)
    flash_len = 0.22 if "flash" in cut.effects else 0.45
    if "flash" in cut.effects or "softflash" in cut.effects:
        graph = (
            f"[0:v]{graph},format=yuv420p,split[base][w];"
            f"[w]drawbox=c=white@1:t=fill,format=rgba,fade=t=out:st=0:d={flash_len}:alpha=1[flash];"
            "[base][flash]overlay=format=auto"
        )
    else:
        graph = f"[0:v]{graph}"
    return graph + f",trim=duration={cut.duration:.3f},format=yuv420p[v]"


def render_edit(plan: EditPlan, music: Path, output: Path, work: Path, ffmpeg: str = "ffmpeg") -> Path:
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, cut in enumerate(plan.cuts):
        part = work / f"cut_{i:03d}.mp4"
        source_len = cut.duration * cut.speed + 0.2
        subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", f"{cut.source_start:.3f}",
             "-t", f"{source_len:.3f}", "-i", str(cut.clip), "-filter_complex",
             _segment_filter(cut), "-map", "[v]", "-an", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "19", "-r", str(FPS), str(part)],
            check=True,
        )
        parts.append(part)

    listing = work / "cuts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = work / "joined.mp4"
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i",
         str(listing), "-c", "copy", str(joined)],
        check=True,
    )
    fade_at = max(0.0, plan.duration - 1.0)
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(joined), "-ss",
         f"{plan.music_start:.3f}", "-t", f"{plan.duration:.3f}", "-i", str(music),
         "-filter_complex", f"[1:a]afade=t=out:st={fade_at:.3f}:d=1[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(output)],
        check=True,
    )
    return output
