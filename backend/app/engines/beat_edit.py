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
import random
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


def envelope(audio: Path, points: int = 240, ffmpeg: str = "ffmpeg") -> list[float]:
    """The track's loudness in `points` steps, 0 to 1 — what the panel
    draws as a waveform under the chosen stretch."""
    signal = _decode_mono(audio, ffmpeg)
    if len(signal) == 0:
        return [0.0] * points
    chunks = np.array_split(np.abs(signal), points)
    levels = np.array([float(np.sqrt((c.astype(np.float64) ** 2).mean())) if len(c) else 0.0 for c in chunks])
    peak = float(levels.max()) or 1.0
    return [round(float(v) / peak, 3) for v in levels]


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

# Share of the frame the subject's movement covers, the median of a few
# seconds inside one shot: over 450 shots of two match compilations, wide
# shots of play sat at 0.01-0.06, a player and his marker at 0.06-0.15,
# and close-ups above that.
_WIDE_LEVEL = 0.06
_CLOSE_LEVEL = 0.16
# Below this nothing is happening at all: a free kick being lined up, a
# pause before a corner, a graphic easing in over them. Never the shot to
# choose for its size alone —
# a still wide shot was the only "wide" a compilation had, so every edit
# opened on the same wall waiting for a kick it then cut away from.
_STILL_LEVEL = 0.012
# With a seed, the shot is drawn from up to this many of a clip's shots
# scoring at least this share of the best — see ClipMotion.busiest.
_VARIETY_POOL = 16
_VARIETY_FLOOR = 0.45
# How far into a wide shot a landscape frame zooms, towards its movement:
# at the plain blurred framing the players were specks.
WIDE_ZOOM = 1.5


def _phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[int, int]:
    """The whole-frame shift from a to b — the camera's movement."""
    spectrum = np.fft.fft2(b) * np.conj(np.fft.fft2(a))
    spectrum /= np.abs(spectrum) + 1e-6
    peak = np.real(np.fft.ifft2(spectrum))
    y, x = np.unravel_index(int(np.argmax(peak)), peak.shape)
    if y > a.shape[0] // 2:
        y -= a.shape[0]
    if x > a.shape[1] // 2:
        x -= a.shape[1]
    return int(y), int(x)


def _activity(frames: np.ndarray, cuts: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Per sample, the share of the frame still changing once the camera's
    own shift is undone, and where across the frame that change sits (0 is
    the left edge, NaN for none). Taken at a cut from the sample before it."""
    out = np.zeros(len(frames), dtype=np.float32)
    focus = np.full(len(frames), np.nan, dtype=np.float32)
    cut_set = set(cuts)
    for i in range(1, len(frames)):
        if i in cut_set:
            out[i] = out[i - 1]
            focus[i] = focus[i - 1]
            continue
        dy, dx = _phase_shift(frames[i - 1], frames[i])
        moved = np.roll(np.roll(frames[i - 1], dy, axis=0), dx, axis=1)
        mask = np.abs(frames[i] - moved)[3:-3, 3:-3] > 22
        out[i] = float(mask.mean())
        columns = mask.sum(axis=0)
        if columns.sum() > 0:
            focus[i] = float((columns * np.arange(len(columns))).sum() / columns.sum() + 3) / (
                frames.shape[2] - 1
            )
    if len(out) > 1:
        out[0] = out[1]
        focus[0] = focus[1]
    return out, focus


@dataclass
class ClipMotion:
    path: Path
    duration_s: float
    scores: np.ndarray  # how much the picture moves, per sample, cuts removed
    # Samples where the clip itself cuts to a new shot. A compilation is
    # full of them, and they are the biggest frame differences in it: left
    # in, "the busiest stretch" meant "the stretch with a cut in it", and
    # every shot of the edit had a second, unplanned cut inside it.
    cuts: list[int] = field(default_factory=list)
    width: int = 0
    height: int = 0
    # Per sample, the share of the frame that moves once the camera's own
    # movement is taken out: the subject, not the pan. Small on a wide
    # shot, where the players are small; large on a close-up.
    activity: np.ndarray | None = None
    # Per sample, where across the frame the movement is (see `_activity`).
    focus: np.ndarray | None = None
    _scales: np.ndarray | None = field(default=None, repr=False)
    _windows: dict[int, np.ndarray] = field(default_factory=dict, repr=False)

    @property
    def landscape(self) -> bool:
        return self.width > self.height

    def shots(self) -> list[tuple[float, float]]:
        """The clip's own shots, as (start, end) seconds."""
        bounds = [0, *self.cuts, len(self.scores)]
        return [
            (bounds[i] / _MOTION_FPS, bounds[i + 1] / _MOTION_FPS)
            for i in range(len(bounds) - 1)
            if bounds[i + 1] > bounds[i]
        ]

    def scale_at(self, index: int) -> str:
        """"wide", "medium" or "close" around a sample, from how much of
        the frame the subject's movement covers (see `activity`)."""
        if self.activity is None or len(self.activity) == 0:
            return "medium"
        if self._scales is None:
            # Once per clip: the planner asks for every candidate window of
            # every cut, which on twelve minutes of footage is hundreds of
            # thousands of questions about the same few thousand samples.
            # Never across one of the clip's own cuts: a compilation cuts
            # every two seconds, and a window reaching into the close-ups
            # either side called nearly every wide shot a close-up.
            act = self.activity
            k = 24
            levels = np.empty(len(act), dtype=np.float32)
            bounds = [0, *[c for c in self.cuts if 0 < c < len(act)], len(act)]
            for a, b in zip(bounds, bounds[1:], strict=False):
                if b <= a:
                    continue
                pad = np.pad(act[a:b], (k, k), mode="edge")
                windows = np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1)
                levels[a:b] = np.median(windows, axis=1)
            self._scales = np.where(
                levels >= _CLOSE_LEVEL, "close", np.where(levels <= _WIDE_LEVEL, "wide", "medium")
            )
        index = min(max(index, 0), len(self._scales) - 1)
        return str(self._scales[index])

    def _window_scores(self, n: int) -> np.ndarray:
        cached = self._windows.get(n)
        if cached is None:
            cached = self._window_scores_uncached(n)
            self._windows[n] = cached
        return cached

    def _window_scores_uncached(self, n: int) -> np.ndarray:
        """Mean action over every window of n samples, each sample judged
        against its own surroundings rather than against the whole clip.

        Raw movement ranks every close-up above every wide shot — a player
        filling the frame moves more pixels walking than a wide shot does
        in a goal — so a long video gave up its close-ups first and its
        wide shots never. Half of the score is how much a moment stands
        out from the few seconds around it, which a wide shot's best
        moment does as much as a close-up's.
        """
        raw = self.scores / (float(np.percentile(self.scores, 95)) or 1.0)
        if self.activity is not None and len(self.activity) == len(self.scores):
            act = self.activity
            k = 6 * _MOTION_FPS
            pad = np.pad(act, (k, k), mode="edge")
            local = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1), axis=1)
            rel = act / (local + 0.01)
            rel = rel / (float(np.percentile(rel, 95)) or 1.0)
            per_sample = 0.5 * np.clip(raw, 0, 1.5) + 0.5 * np.clip(rel, 0, 1.5)
        else:
            per_sample = raw
        means = np.convolve(per_sample, np.ones(n), mode="valid") / n
        if n < 4:
            return means
        # Where the peak falls inside the shot. A moment worth showing has
        # a lead-in and a payoff — the run-up and then the kick — and a
        # window that ends on its biggest movement cuts away at the strike,
        # while one that starts on it begins after the thing happened.
        # Peaks from 40% to 85% of the way through keep their score; the
        # further outside that, the less they keep.
        peaks = np.argmax(np.lib.stride_tricks.sliding_window_view(per_sample, n), axis=1)
        position = peaks / (n - 1)
        early = np.clip((0.4 - position) / 0.4, 0, 1)
        late = np.clip((position - 0.85) / 0.15, 0, 1)
        return means * (1.0 - 0.6 * np.maximum(early, late))

    def still(self, start: float, length_s: float) -> bool:
        """Nothing moves in this stretch — see `_STILL_LEVEL`."""
        if self.activity is None or len(self.activity) == 0:
            return False
        a = int(start * _MOTION_FPS)
        b = max(a + 1, int((start + length_s) * _MOTION_FPS))
        # Judged over the whole of the clip's own shot around it, and by the
        # median: a compilation flashes into a shot, every pixel moving for
        # a frame or two, and a short window over that flash read as action
        # in a shot where nothing else moves.
        for lo, hi in zip([0, *self.cuts], [*self.cuts, len(self.activity)], strict=False):
            if lo <= a < hi:
                a, b = lo, max(b, hi)
                break
        return float(np.median(self.activity[a:b])) < _STILL_LEVEL

    def focus_at(self, start: float, length_s: float) -> float:
        """Where across the frame a stretch's movement is, 0 to 1; the
        middle when nothing moves."""
        if self.focus is None or len(self.focus) == 0:
            return 0.5
        a = int(start * _MOTION_FPS)
        b = max(a + 1, int((start + length_s) * _MOTION_FPS))
        values = self.focus[a:b]
        values = values[~np.isnan(values)]
        return float(np.median(values)) if len(values) else 0.5

    def busiest(
        self,
        length_s: float,
        avoid: list[tuple[float, float]],
        prefer: str | tuple[str, ...] | None = None,
        spread_s: float = 0.0,
        rng: random.Random | None = None,
    ) -> float | None:
        """Start of the best `length_s` stretch that sits inside one of the
        clip's own shots and overlaps nothing in `avoid`; None if no shot
        is long enough.

        `prefer` favours a shot scale ("wide", "medium", "close") so an
        edit can alternate them. `spread_s` pushes the choice away from
        stretches already used, so twelve minutes of footage is drawn on
        across its length instead of from its first good minute.

        With `rng`, any shot within reach of the best is a fair pick, so a
        second edit of the same footage is not the first one again."""
        n = max(1, int(round(length_s * _MOTION_FPS)))
        if len(self.scores) < n:
            return None
        sums = self._window_scores(n)
        margin = 0.04
        # The preferred sizes, in order, win whenever the clip has them,
        # however little moves in them: an establishing wide shot scores
        # near nothing on action and is still the right shot for the
        # build-up. Without any of them, the best of anything.
        order = (prefer,) if isinstance(prefer, str) else tuple(prefer or ())
        rank = {size: i for i, size in enumerate(order)}
        # Per size level, the best window of each shot: (start, score).
        best: dict[int, dict[int, tuple[float, float]]] = {}
        for shot_no, (shot_start, shot_end) in enumerate(self.shots()):
            first = int(math.ceil((shot_start + margin) * _MOTION_FPS))
            last = int(math.floor((shot_end - margin - length_s) * _MOTION_FPS))
            for index in range(max(first, 0), min(last, len(sums) - 1) + 1):
                start = index / _MOTION_FPS
                end = start + length_s
                if end > self.duration_s - 0.05:
                    continue
                if any(not (end <= a or start >= b) for a, b in avoid):
                    continue
                score = float(sums[index])
                if spread_s > 0 and avoid:
                    gap = min(max(a - end, start - b, 0.0) for a, b in avoid)
                    score *= 0.35 + 0.65 * min(1.0, gap / spread_s)
                level = rank.get(self.scale_at(index + n // 2), len(order))
                if level < len(order) and self.still(start, length_s):
                    # Right size, nothing in it: only if nothing else is left.
                    level, score = len(order) + 1, score * 0.3
                shots = best.setdefault(level, {})
                current = shots.get(shot_no)
                if current is None or score > current[1]:
                    shots[shot_no] = (float(start), score)
        if not best:
            return None
        choices = sorted(best[min(best)].values(), key=lambda c: -c[1])
        if rng is None:
            return choices[0][0]
        # A wide pool, weighted by how good each shot is. Picking among
        # only the few nearly-best ones meant two edits of the same footage
        # shared half their shots and opened on the same three; users saw
        # "the same video again" on every retry.
        top = choices[0][1]
        pool = [c for c in choices if c[1] >= _VARIETY_FLOOR * top][:_VARIETY_POOL]
        weights = [max(c[1], 1e-6) ** 2 for c in pool]
        return rng.choices(pool, weights=weights, k=1)[0][0]

    def fits(self, start: float, length_s: float, avoid: list[tuple[float, float]]) -> bool:
        """Whether `length_s` from `start` stays inside one of the clip's
        own shots and clear of everything in `avoid`."""
        end = start + length_s
        if end > self.duration_s - 0.05:
            return False
        if any(not (end <= a or start >= b) for a, b in avoid):
            return False
        return any(a <= start and end <= b - 0.04 for a, b in self.shots())

    def longest_free_shot(self, avoid: list[tuple[float, float]]) -> tuple[float, float] | None:
        """The longest of the clip's shots not yet used — for a cut longer
        than any shot, which is then slowed to fill it."""
        free = [
            (a, b)
            for a, b in self.shots()
            if b - a > 0.2 and all(b <= x or a >= y for x, y in avoid)
        ]
        # A shot where something happens before a longer one where nothing does.
        return max(free, key=lambda s: (not self.still(s[0], s[1] - s[0]), s[1] - s[0])) if free else None


def _histograms(frames: np.ndarray) -> np.ndarray:
    """Per frame: a 3x3 grid of 8-bin colour histograms, normalised.

    What changes at a cut and not in a pan. A camera whipping after the
    ball moves every pixel — on a broadcast the plain frame difference
    sits that high for whole seconds, and a cut stops standing out from
    it — but each region keeps roughly the same colours. A cut replaces
    them.
    """
    n, h, w, _ = frames.shape
    rows, cols = h // 3, w // 3
    out = np.empty((n, 9 * 24), dtype=np.float32)
    for gy in range(3):
        for gx in range(3):
            block = frames[:, gy * rows : (gy + 1) * rows, gx * cols : (gx + 1) * cols]
            for c in range(3):
                values = (block[..., c] // 32).reshape(n, -1).astype(np.int64)
                counts = np.stack([np.bincount(v, minlength=8) for v in values])
                start = (gy * 3 + gx) * 24 + c * 8
                out[:, start : start + 8] = counts / max(1, values.shape[1])
    return out


def _source_cuts(changes: np.ndarray, floor: float = 0.45) -> list[int]:
    """Samples where the picture's make-up changes far more than around it:
    a cut, not motion. `changes[i]` is the change between sample i and
    i + 1; the result is the first sample of each new shot."""
    cuts: list[int] = []
    n = len(changes)
    for i in range(n):
        lo, hi = max(0, i - 12), min(n, i + 13)
        neighbours = np.concatenate([changes[lo:i], changes[i + 1 : hi]])
        local = float(np.median(neighbours)) if len(neighbours) else 0.0
        if changes[i] > max(floor, 3.0 * local):
            cuts.append(i + 1)
    # One cut can register on two neighbouring samples; keep the first.
    return [c for k, c in enumerate(cuts) if k == 0 or c - cuts[k - 1] > 2]


def motion_profile(clip: Path, ffmpeg: str = "ffmpeg", ffprobe: str | None = None) -> ClipMotion:
    if ffprobe is None:
        ffprobe = ffmpeg[: -len("ffmpeg")] + "ffprobe" if ffmpeg.endswith("ffmpeg") else "ffprobe"
    probe = subprocess.run(
        [ffprobe,
         "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:stream_side_data=rotation", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True,
    ).stdout.strip().splitlines()
    width = height = 0
    if probe:
        parts = [p for p in probe[0].split(",") if p.strip()]
        if len(parts) >= 2:
            width, height = int(parts[0]), int(parts[1])
            rotation = next((int(float(p)) for p in parts[2:] if p.strip("-").isdigit()), 0)
            if abs(rotation) in (90, 270):
                width, height = height, width
    # Sampled in the clip's own shape, so a landscape frame is not squeezed
    # into a portrait one before anything is measured on it.
    aw, ah = (_MOTION_H, _MOTION_W) if width > height else (_MOTION_W, _MOTION_H)
    raw = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-i", str(clip), "-vf",
         f"fps={_MOTION_FPS},scale={aw}:{ah},format=rgb24",
         "-f", "rawvideo", "-"],
        check=True, capture_output=True,
    ).stdout
    rgb = np.frombuffer(raw, dtype=np.uint8).reshape(-1, ah, aw, 3)
    frames = rgb.astype(np.float32).mean(axis=3)
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2)) if len(frames) > 1 else np.zeros(1)
    if len(rgb) > 1:
        hist = _histograms(rgb)
        cuts = _source_cuts(np.abs(np.diff(hist, axis=0)).sum(axis=1) / 9)
    else:
        cuts = []
    cleaned = diffs.copy()
    for c in cuts:
        i = c - 1
        lo, hi = max(0, i - 6), min(len(diffs), i + 7)
        cleaned[i] = float(np.median(diffs[lo:hi]))
    scores = np.concatenate([[cleaned[0] if len(cleaned) else 0.0], cleaned])
    activity, focus = _activity(frames, cuts) if len(frames) > 1 else (None, None)
    return ClipMotion(
        path=clip, duration_s=len(frames) / _MOTION_FPS, scores=scores,
        cuts=cuts, width=width, height=height,
        activity=activity, focus=focus,
    )


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
    # Filmed wider than tall: shown whole over a blurred fill rather than
    # cropped to a vertical sliver of its middle.
    landscape: bool = False
    # A landscape wide shot is shown closer, `zoom` times the plain framing,
    # centred `focus_x` of the way across the source (0 is its left edge).
    zoom: float = 1.0
    focus_x: float = 0.5
    # A landscape close-up or medium shot fills the vertical frame instead:
    # cropped to a third of its width around the player (`focus_x`), the
    # way a fan edit cuts a broadcast into a face. Wide shots keep the
    # blurred frame, which keeps their context.
    close_crop: bool = False
    # A speed ramp across the cut: (share of the cut on the timeline, speed)
    # pieces in order. `speed` above is then their average, which is what
    # the stretch of source taken is measured by.
    ramp: tuple[tuple[float, float], ...] | None = None


# Fast into the moment, slow through it, quick out: the velocity edit. The
# slow piece sits where the planner's windows put the peak (40-85% in).
RAMP_HARD: tuple[tuple[float, float], ...] = ((0.35, 1.8), (0.35, 0.45), (0.30, 1.4))
RAMP_SOFT: tuple[tuple[float, float], ...] = ((0.30, 1.4), (0.45, 0.55), (0.25, 1.15))
# A ramp needs room: under this a cut is one beat of motion, and three
# speeds in it read as a stutter.
_RAMP_MIN_S = 0.9


def ramp_speed(ramp: tuple[tuple[float, float], ...]) -> float:
    """Seconds of source per second of timeline, over a whole ramp."""
    return sum(share * speed for share, speed in ramp)


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
    # Which shot sizes of a landscape source fill the frame (see Cut).
    close_crop_scales: tuple[str, ...] = ()
    # The speed ramp, and how often a cut gets one (every nth eligible cut).
    ramp: tuple[tuple[float, float], ...] | None = None
    ramp_every: int = 0


STYLES: dict[str, Style] = {
    # Two beats a cut after the drop, not one: at one, 120 BPM is a new
    # shot every half second, which reads as noise rather than energy.
    "energetic": Style(
        4, 2, "punch", ("flash", "rgbsplit", "shake"), 0.5, "shake", "grade",
        close_crop_scales=("close", "medium"), ramp=RAMP_HARD, ramp_every=2,
    ),
    # Long enough to read a move from start to finish: two bars before the
    # drop, one after — about four and two seconds at 120 BPM. At two and
    # one beats it was cutting every second, which reads as fast however
    # soft the grade.
    "cinematic": Style(
        8, 4, "drift", ("softflash",), 0.5, None, "grade_film",
        close_crop_scales=("close", "medium"), ramp=RAMP_SOFT, ramp_every=3,
    ),
    "calm": Style(8, 8, "drift", (), 1.0, None, "grade_soft", close_crop_scales=("close",)),
}


def default_start(grid: BeatGrid, target_s: float) -> float:
    """Where in the track an edit starts when nobody chose: on a bar, so
    the drop lands about a third of the way in — long enough to build,
    early enough to pay off. The first bar when there is no drop."""
    target_s = min(target_s, max(4.0, grid.duration_s - 0.5))
    if grid.drop_s is not None:
        wanted = grid.drop_s - target_s * 0.33
        starts = [b for b in grid.downbeats if b <= wanted] or grid.downbeats[:1]
        start = starts[-1]
    else:
        start = grid.downbeats[0] if grid.downbeats else 0.0
    return max(0.0, min(start, grid.duration_s - target_s))


def plan_edit(
    grid: BeatGrid,
    clips: list[ClipMotion],
    target_s: float = 16.0,
    style: str = "energetic",
    music_start: float | None = None,
    seed: int | None = None,
) -> EditPlan:
    """Which clip, which stretch and which effect sits on each beat.

    Built around the drop: a build-up cut every few beats, then the drop
    with the style's heaviest effect and a slow-motion hit, then cuts on
    the beat to the end. `music_start` overrides where in the track the
    edit begins; by default the drop lands about a third of the way in.
    `seed` varies the choice among equally good shots, so two edits of the
    same footage differ; without one the plan is the same every time.
    """
    rng = random.Random(seed) if seed is not None else None
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
    else:
        music_start = default_start(grid, target_s)
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
    if rng is not None:
        # The busiest clip first only when nobody asked for variety.
        rng.shuffle(order)
    cuts: list[Cut] = []
    last: Path | None = None
    turn = 0
    beat_set = [b for b in timeline]
    # The slowest a shot is stretched to fill a cut. Past half speed,
    # without frame interpolation, motion stutters.
    min_speed = 0.5
    queue = [(points[k], points[k + 1]) for k in range(len(points) - 1)]
    last_scales: list[str] = []
    k = 0
    ramped_turn = 0
    while queue:
        start, end = queue.pop(0)
        length = end - start
        if length < 0.08:
            continue
        is_drop = drop is not None and abs(start - drop) < 0.05
        speed = look.drop_speed if is_drop else 1.0
        ramp = None

        # Every clip in turn, busiest first, never the same one twice running.
        clip = order[turn % len(order)]
        if clip.path == last and len(order) > 1:
            turn += 1
            clip = order[turn % len(order)]

        source_len = length * speed
        # A mix of shot sizes, shaped by the music: wide and medium while it
        # builds, the close-up on the drop, then close-ups broken up by wide
        # ones. Never the same size three times running.
        after = drop is not None and start >= drop - 0.01
        prefer: tuple[str, ...]
        if is_drop:
            prefer = ("close", "medium")
        elif after:
            prefer = ("wide", "medium") if last_scales[-1:] == ["close"] else ("close", "medium")
        else:
            prefer = ("medium", "wide") if last_scales[-1:] == ["wide"] else ("wide", "medium")
        if len(last_scales) >= 2 and last_scales[-1] == last_scales[-2] == prefer[0]:
            prefer = ("medium", *[p for p in prefer if p != "medium"])

        spread = max(2.0, min(30.0, clip.duration_s / max(1.0, len(points) * 1.2)))
        src = clip.busiest(source_len, used[clip.path], prefer=prefer, spread_s=spread, rng=rng)
        if src is None:
            # No shot of this clip is long enough at this speed. Slow its
            # longest free shot to fill the cut if half speed is enough;
            # if not, the cut is longer than this footage can hold in one
            # piece, so it becomes two cuts at the beat nearest its middle
            # — a cut on the beat rather than one the source makes for us.
            shot = clip.longest_free_shot(used[clip.path])
            available = max(0.1, (shot[1] - shot[0] - 0.08) if shot else clip.duration_s - 0.1)
            inside = [b for b in beat_set if start + 0.2 < b < end - 0.2]
            if available / length < min_speed and inside:
                middle = min(inside, key=lambda b: abs(b - (start + end) / 2))
                queue[:0] = [(start, middle), (middle, end)]
                continue
            # No beat to split on: stretch further rather than cut mid-beat.
            floor = min_speed if available / length >= min_speed else 0.25
            ramp = None  # a stretched shot is slow already
            speed = max(floor, min(speed, available / length))
            source_len = length * speed
            src = (shot[0] + 0.04) if shot else 0.0
            if src + source_len > clip.duration_s:
                src = max(0.0, clip.duration_s - source_len - 0.05)
        turn += 1

        effects: list[str] = [look.grade]
        if is_drop:
            effects += list(look.drop_effects)
        elif round(start, 3) in downbeats:
            effects.append(look.bar_effect)
        elif look.after_drop_extra and drop is not None and start > drop and k % 3 == 0:
            effects.append(look.after_drop_extra)
        else:
            effects.append("drift")
        k += 1

        scale = clip.scale_at(int((src + source_len / 2) * _MOTION_FPS))
        # The ramp goes where it reads, judged on the shot actually taken:
        # a close or medium one, every so often. On a wide shot the slow
        # piece is a field of small players drifting; on a close-up it is
        # the moment. The drop has its own slow motion. A ramp reads more
        # source than a plain cut, so it is only applied when that much
        # more fits in the same shot.
        if (
            look.ramp
            and look.ramp_every
            and not is_drop
            and speed == 1.0
            and length >= _RAMP_MIN_S
            and scale in ("close", "medium")
        ):
            if ramped_turn % look.ramp_every == 0:
                need = length * ramp_speed(look.ramp)
                if clip.fits(src, need, used[clip.path]):
                    ramp = look.ramp
                    speed = ramp_speed(ramp)
                    source_len = need
            ramped_turn += 1
        last_scales.append(scale)
        used[clip.path].append((src, src + source_len))
        zoom, focus_x = 1.0, 0.5
        close_crop = clip.landscape and scale in look.close_crop_scales
        if close_crop:
            # Where the movement is; the render refines it to a face when
            # one is found (render_manager), which is what a close-up of a
            # player is framed on.
            focus_x = clip.focus_at(src, source_len)
        elif clip.landscape and scale == "wide":
            # Half way from the middle towards the movement: the camera
            # already follows the ball, and the movement's centre is
            # pulled about by players far from it.
            zoom = WIDE_ZOOM
            focus_x = 0.5 + 0.5 * (clip.focus_at(src, source_len) - 0.5)
        cuts.append(
            Cut(
                clip=clip.path, source_start=src, duration=length, speed=speed,
                effects=effects, landscape=clip.landscape, zoom=zoom, focus_x=focus_x,
                close_crop=close_crop, ramp=ramp,
            )
        )
        last = clip.path

    return EditPlan(music_start=music_start, duration=points[-1] - points[0], cuts=cuts)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


# How long the end of an edit takes to go to black and silence.
FADE_OUT_S = 1.5


def _segment_filter(cut: Cut) -> str:
    """The filter graph for one cut, its clock starting at zero."""
    cover = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1"
    )
    if cut.ramp:
        # Each piece of the ramp is its own stretch of source at its own
        # speed, and the pieces are joined back into one clip.
        pieces, labels, offset = [], [], 0.0
        for n, (share, speed) in enumerate(cut.ramp):
            source_s = share * cut.duration * speed
            pieces.append(
                f"[r{n}]trim=start={offset:.4f}:duration={source_s:.4f},"
                f"setpts=(PTS-STARTPTS)/{speed:.4f}[p{n}]"
            )
            labels.append(f"[p{n}]")
            offset += source_s
        split = "".join(f"[r{n}]" for n in range(len(cut.ramp)))
        timed = (
            f"[0:v]setpts=PTS-STARTPTS,split={len(cut.ramp)}{split};"
            + ";".join(pieces)
            + f";{''.join(labels)}concat=n={len(cut.ramp)}:v=1:a=0,fps={FPS}[tv];"
        )
    else:
        timed = f"[0:v]setpts={1 / cut.speed:.4f}*(PTS-STARTPTS),fps={FPS}[tv];"
    if cut.landscape and cut.close_crop:
        # A third of the width at full height, around the player.
        x = f"min(max({cut.focus_x:.3f}*iw-{WIDTH}/2,0),iw-{WIDTH})"
        framing = (
            f"{timed}[tv]scale=-2:{HEIGHT},crop={WIDTH}:{HEIGHT}:x='{x}':y=0,setsar=1[framed];"
        )
    elif cut.landscape:
        # A landscape shot cropped to fill a vertical frame keeps a third
        # of its width: on a match broadcast that was legs, a referee and
        # an advertising board, with the player somewhere off the edge.
        # Here three quarters of the width stays in the middle, and the
        # space above and below is the same picture blurred and darkened,
        # which is how a fan edit fills it.
        wide = int(WIDTH * 4 / 3 * cut.zoom) // 2 * 2
        x = f"min(max({cut.focus_x:.3f}*iw-{WIDTH}/2,0),iw-{WIDTH})"
        framing = (
            f"{timed}[tv]split[s1][s2];"
            f"[s1]{cover},boxblur=20:2,eq=brightness=-0.12:saturation=0.8[bg];"
            f"[s2]scale={wide}:-2,crop={WIDTH}:ih:x='{x}',setsar=1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[framed];"
        )
    else:
        framing = f"{timed}[tv]{cover}[framed];"
    chain: list[str] = []
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
    graph = ",".join(chain) or "null"
    flash_len = 0.22 if "flash" in cut.effects else 0.45
    if "flash" in cut.effects or "softflash" in cut.effects:
        graph = (
            f"{framing}[framed]{graph},format=yuv420p,split[base][w];"
            f"[w]drawbox=c=white@1:t=fill,format=rgba,fade=t=out:st=0:d={flash_len}:alpha=1[flash];"
            "[base][flash]overlay=format=auto"
        )
    else:
        graph = f"{framing}[framed]{graph}"
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
    # The ending: picture and music go out together — to black and to
    # silence over the same stretch — so the edit finishes rather than
    # stops, and loops cleanly where it is played on repeat. The video is
    # re-encoded for it; the cuts were joined by stream copy, and a fade
    # cannot be.
    fade_s = min(FADE_OUT_S, plan.duration / 4)
    fade_at = max(0.0, plan.duration - fade_s)
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(joined), "-ss",
         f"{plan.music_start:.3f}", "-t", f"{plan.duration:.3f}", "-i", str(music),
         "-filter_complex",
         f"[0:v]fade=t=out:st={fade_at:.3f}:d={fade_s:.3f}:color=black[v];"
         f"[1:a]afade=t=out:st={fade_at:.3f}:d={fade_s:.3f}[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(output)],
        check=True,
    )
    return output
