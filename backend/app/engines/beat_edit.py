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
from functools import partial
from pathlib import Path

import numpy as np

from app.core.config import FONTS_DIR

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
# Share of a sample's pixels with no edge to their neighbours. A YouTube
# end screen ("check out these videos"), a title card or a subscribe slate
# is flat colour behind a few words: 0.75 on one that ended up in an edit,
# against 0.13-0.47 for every shot of play around it, dark night matches
# included.
_FLAT_LEVEL = 0.6
# With a seed, the shot is drawn from up to this many of a clip's shots
# scoring at least this share of the best — see ClipMotion.busiest.
_VARIETY_POOL = 16
_VARIETY_FLOOR = 0.45
# How far into a wide shot a landscape frame zooms, towards its movement:
# at the plain blurred framing the players were specks.
WIDE_ZOOM = 1.5
# A close or medium shot with no face to crop to stays in the blurred
# frame but closer than a wide one: the action fills it, and a whip pan in
# the source still has its edges around it rather than filling the screen.
NEAR_ZOOM = 1.9


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
    # Per sample, the share of the picture that is flat colour (see
    # `_FLAT_LEVEL` and `_flatness`).
    flat: np.ndarray | None = None
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

    def graphic(self, start: float, end: float) -> bool:
        """Whether a stretch is not footage but a screen laid over it: an end
        screen, a title card, the black between a countdown's entries.
        Nothing moves in it and it is mostly flat colour. Never shown — a
        still shot of play is a weak choice, this is a wrong one.

        Flatness alone, not where in the video it sits: "still, in the last
        twenty seconds" also took a free kick being lined up at the end of a
        goals countdown."""
        if self.activity is None or len(self.activity) == 0:
            return False
        a = int(start * _MOTION_FPS)
        b = max(a + 1, int(end * _MOTION_FPS))
        if self.flat is None or len(self.flat) == 0:
            return False
        return (
            float(np.median(self.activity[a:b])) < _STILL_LEVEL
            and float(np.median(self.flat[a:b])) > _FLAT_LEVEL
        )

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
        used_before: list[tuple[float, float]] | None = None,
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
                if self.graphic(shot_start, shot_end):
                    break
                score = float(sums[index])
                if spread_s > 0 and avoid:
                    gap = min(max(a - end, start - b, 0.0) for a, b in avoid)
                    score *= 0.35 + 0.65 * min(1.0, gap / spread_s)
                if used_before and any(not (end <= a or start >= b) for a, b in used_before):
                    # Shown in one of the last edits of this footage: still
                    # possible, much less likely, so another try is another
                    # edit rather than the same strongest moments again.
                    score *= 0.25
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
            if b - a > 0.2 and all(b <= x or a >= y for x, y in avoid) and not self.graphic(a, b)
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


def _flatness(frames: np.ndarray) -> np.ndarray:
    """Per grey frame, the share of pixels within a level or so of every
    neighbour: flat colour. Footage has grain, grass and crowd in it even
    when dark; a graphic does not."""
    if frames.shape[1] < 2 or frames.shape[2] < 2:
        return np.zeros(len(frames), dtype=np.float32)
    across = np.abs(np.diff(frames, axis=2))[:, :-1, :]
    down = np.abs(np.diff(frames, axis=1))[:, :, :-1]
    return (np.maximum(across, down) < 1.5).mean(axis=(1, 2)).astype(np.float32)


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
        activity=activity, focus=focus, flat=_flatness(frames),
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
    # How long one moment runs on the timeline, and how many of the
    # source's own consecutive shots it may span (a move and its replay).
    moment_min_s: float = 1.4
    moment_max_s: float = 3.2
    moment_shots: int = 1


STYLES: dict[str, Style] = {
    # Each cut is a whole moment — a move from its start to its end —
    # rounded to the beats, never a beat-length slice of one. Energetic is
    # the hits and the flashes, not the shortest cuts: at a cut every beat
    # nobody could tell what had happened.
    "energetic": Style(
        4, 2, "punch", ("flash", "rgbsplit", "shake"), 0.75, "shake", "grade",
        close_crop_scales=("close", "medium"),
        moment_min_s=1.4, moment_max_s=3.2, moment_shots=1,
    ),
    "cinematic": Style(
        8, 4, "drift", ("softflash",), 0.75, None, "grade_film",
        close_crop_scales=("close", "medium"),
        moment_min_s=2.2, moment_max_s=5.0, moment_shots=2,
    ),
    "calm": Style(
        8, 8, "drift", (), 1.0, None, "grade_soft", close_crop_scales=("close",),
        moment_min_s=3.0, moment_max_s=6.5, moment_shots=3,
    ),
}


# How close an action shot of a landscape source is framed: the whole move
# in view, a little closer than the plain blurred frame.
ACTION_ZOOM = 1.25
# A moment is stretched or squeezed to the beats by at most this much.
_SPEED_RANGE = (0.85, 1.2)


@dataclass
class Moment:
    """One run of the source's own shots that reads as a single thing."""

    index: int
    clip: ClipMotion
    start: float
    end: float
    score: float
    close: bool

    @property
    def length(self) -> float:
        return self.end - self.start


def _add_moment(
    out: list[Moment], clip: ClipMotion, per_sample: np.ndarray, a: float, b: float
) -> None:
    lo = int(a * _MOTION_FPS)
    hi = max(lo + 1, int(b * _MOTION_FPS))
    score = float(np.mean(per_sample[lo:hi])) if hi <= len(per_sample) else 0.0
    middle = int((a + b) / 2 * _MOTION_FPS)
    out.append(Moment(len(out), clip, a, b, score, clip.scale_at(middle) == "close"))


def _moments(clips: list[ClipMotion], look: Style) -> list[Moment]:
    """Every candidate moment: each of the clips' own shots, and runs of up
    to `look.moment_shots` consecutive ones, long enough to be a moment
    and not much longer than one. A shot far longer than a moment — a
    single uncut video — is offered as overlapping stretches of it."""
    out: list[Moment] = []
    longest = look.moment_max_s * 1.4
    for clip in clips:
        shots = clip.shots()
        add = partial(_add_moment, out, clip, clip._window_scores(1))

        # A run never takes in an end screen or a title card, as its own
        # moment or as the tail of one.
        graphic = [clip.graphic(a, b) for a, b in shots]

        for n, (a, _b) in enumerate(shots):
            for span in range(1, look.moment_shots + 1):
                if n + span > len(shots) or graphic[n + span - 1]:
                    break
                b = shots[n + span - 1][1]
                if b - a > longest:
                    if span == 1:
                        step = look.moment_max_s / 2
                        t = a
                        while t + look.moment_max_s <= b:
                            add(t, t + look.moment_max_s)
                            t += step
                    break
                if b - a >= look.moment_min_s * 0.75:
                    add(a, b)
    return out


def _pick_moment(
    moments: list[Moment],
    role: str,
    taken: set[int],
    used: dict[Path, list[tuple[float, float]]],
    history: dict[Path, list[tuple[float, float]]],
    last_clip: Path | None,
    rng: random.Random | None,
    spread: dict[Path, float] | None = None,
) -> Moment | None:
    """The moment for a role, from those not overlapping anything used.
    The hero is the strongest action; others are drawn by weight with a
    seed, so another edit of the same footage is another edit."""

    def clear(m: Moment) -> bool:
        return m.index not in taken and all(
            m.end <= a or m.start >= b for a, b in used.get(m.clip.path, [])
        )

    def weight(m: Moment) -> float:
        w = m.score
        mine = used.get(m.clip.path, [])
        if mine:
            # Spread over the footage: a long video is drawn on across its
            # length, not from its first good minute.
            reach = (spread or {}).get(m.clip.path, 2.0)
            gap = min(max(a - m.end, m.start - b, 0.0) for a, b in mine)
            w *= 0.35 + 0.65 * min(1.0, gap / reach)
        if any(not (m.end <= a or m.start >= b) for a, b in history.get(m.clip.path, [])):
            w *= 0.25
        if m.clip.path == last_clip and len({x.clip.path for x in moments}) > 1:
            w *= 0.2
        return w

    pool = [m for m in moments if clear(m)]
    if not pool:
        return None
    wanted_close = role == "reaction"
    fitting = [m for m in pool if m.close == wanted_close] if role != "hero" else [
        m for m in pool if not m.close
    ]
    pool = fitting or pool
    ranked = sorted(pool, key=lambda m: -weight(m))
    if role == "hero" or rng is None:
        return ranked[0]
    top = weight(ranked[0])
    near = [m for m in ranked if weight(m) >= _VARIETY_FLOOR * top][:_VARIETY_POOL]
    return rng.choices(near, weights=[max(weight(m), 1e-6) ** 2 for m in near], k=1)[0]


def _fit_to_beats(
    moment: Moment, period: float, look: Style, limit: int, is_drop: bool
) -> tuple[int, float, float]:
    """How many beats a moment takes, how much of it is read and at what
    speed: the beat count nearest its length, within the style's range and
    `limit`, played between 0.85x and 1.2x so it fills them exactly — the
    hero on the drop a little slower."""
    lo, hi = _SPEED_RANGE
    if is_drop:
        lo, hi = look.drop_speed * 0.9, look.drop_speed * 1.1 if look.drop_speed < 1 else hi
    usable = moment.length - 0.08
    min_b = max(1, math.ceil(look.moment_min_s / period - 0.15))
    max_b = max(min_b, math.floor(look.moment_max_s / period + 0.15))
    ideal = round(usable / (period * (lo + hi) / 2))
    beats_n = min(max(ideal, min_b), max_b, max(1, limit))
    # Never leave a sliver before the drop or the end: a beat or two left
    # over is taken into this cut, or left as a whole moment's worth for
    # the next one — not played as half a second of something.
    rest = limit - beats_n
    if 0 < rest < min_b:
        beats_n = limit if limit <= max_b + min_b - 1 else limit - min_b
    timeline_len = beats_n * period
    # Stretched a little further than usual when it had to take the
    # leftover beats, rather than cut short.
    speed = min(max(usable / timeline_len, min(lo, 0.7)), hi)
    return beats_n, timeline_len * speed, speed


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
    history: dict[Path, list[tuple[float, float]]] | None = None,
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

    period = 60.0 / grid.tempo_bpm
    drop_index = (
        next((j for j, b in enumerate(timeline) if b >= drop - 0.01), None) if drop is not None else None
    )
    moments = _moments(clips, look)
    if not moments:
        raise ValueError("None of those clips has a moment long enough to cut to.")
    used: dict[Path, list[tuple[float, float]]] = {c.path: [] for c in clips}
    # How far apart a clip's moments are pushed: its length over the number
    # of moments this edit will take from it, roughly.
    expected = max(4.0, target_s / ((look.moment_min_s + look.moment_max_s) / 2))
    reach = {
        c.path: max(2.0, min(60.0, c.duration_s * len(clips) / (expected * 1.2))) for c in clips
    }
    taken: set[int] = set()
    cuts: list[Cut] = []
    i = 0
    last_clip: Path | None = None
    since_reaction = 0
    while i < len(timeline) - 1:
        is_drop = drop_index is not None and i == drop_index
        after = drop_index is not None and i >= drop_index
        remaining = len(timeline) - 1 - i
        # The story: a reaction to open, action building to the hero moment
        # on the drop, action after it with a reaction now and then, and a
        # reaction to close. A reaction is a close shot — a face, if one is
        # found when it is framed — and an action shot shows the whole move.
        if not cuts:
            role = "reaction"
        elif is_drop:
            role = "hero"
        elif remaining * period <= look.moment_max_s * 1.3:
            # What is left is one moment's worth: the last cut, a reaction.
            role = "reaction"
        elif since_reaction >= (2 if after else 3):
            role = "reaction"
        else:
            role = "action"
        # How far this cut may run: to the drop, to the end, or a moment's
        # longest.
        limit = remaining
        if drop_index is not None and i < drop_index:
            limit = drop_index - i
        moment = _pick_moment(
            moments, role, taken, used, history or {}, last_clip, rng, reach,
        )
        if moment is None:
            break
        beats_n, source_len, speed = _fit_to_beats(moment, period, look, limit, is_drop)
        end_i = min(i + beats_n, len(timeline) - 1)
        length = timeline[end_i] - timeline[i]
        if length < 0.08:
            break
        source_len = min(source_len, length * speed)
        speed = source_len / length
        # The end of the moment is kept: the source cut after its payoff, and
        # so does this — a cut that ends early is the shot before the goal.
        src = moment.end - 0.04 - source_len
        if role == "reaction":
            src = moment.start + max(0.0, (moment.length - source_len) / 2)
        src = max(moment.start, src)
        clip = moment.clip
        taken.add(moment.index)
        used[clip.path].append((src, src + source_len))

        effects: list[str] = [look.grade]
        start_t = timeline[i]
        if is_drop:
            effects += list(look.drop_effects)
        elif round(start_t, 3) in downbeats:
            effects.append(look.bar_effect)
        elif look.after_drop_extra and after and len(cuts) % 3 == 0:
            effects.append(look.after_drop_extra)
        else:
            effects.append("drift")

        scale = clip.scale_at(int((src + source_len / 2) * _MOTION_FPS))
        close_crop = clip.landscape and role == "reaction" and scale in look.close_crop_scales
        zoom, focus_x = 1.0, 0.5
        if close_crop:
            focus_x = clip.focus_at(src, source_len)
        elif clip.landscape:
            # The whole move in view, a little closer than the plain frame:
            # what is happening has to be readable before it is pretty.
            zoom = ACTION_ZOOM
            focus_x = 0.5 + 0.5 * (clip.focus_at(src, source_len) - 0.5)
        cuts.append(
            Cut(
                clip=clip.path, source_start=src, duration=length, speed=speed,
                effects=effects, landscape=clip.landscape, zoom=zoom, focus_x=focus_x,
                close_crop=close_crop,
            )
        )
        since_reaction = 0 if role == "reaction" else since_reaction + 1
        last_clip = clip.path
        i = end_i

    return EditPlan(
        music_start=music_start, duration=timeline[i] - timeline[0], cuts=cuts
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


# How long the end of an edit takes to go to black and silence.
FADE_OUT_S = 1.5
# How long the start takes to come up out of them: short, so the opening
# shot and the first beat still land.
FADE_IN_S = 0.8


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


# The opening title: when it starts, how fast its words type in, how long
# it holds once complete, and how long it takes to go.
TITLE_START_S = 0.25
TITLE_WORD_S = 0.2
TITLE_HOLD_S = 2.2
TITLE_FADE_S = 0.35


def _ass_text(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def title_ass(text: str, path: Path, duration: float) -> Path | None:
    """The opening title as an ASS file: bold white words with a warm glow,
    each fading and popping in after the last, on one or two lines in the
    top band, above where a close-up puts the face, then
    the whole line fading out. None when there is no text.

    Drawn by libass in the same pass as the closing fade, so it costs no
    extra encode — and in the font the captions ship with."""
    words = text.split()
    if not words:
        return None
    # Two lines once it is long enough to need them, split near the middle.
    if len(" ".join(words)) > 14 and len(words) > 1:
        half = len(" ".join(words)) / 2
        run, split_at = 0, 1
        for n, w in enumerate(words[:-1], start=1):
            run += len(w) + 1
            if run >= half:
                split_at = n
                break
        lines = [words[:split_at], words[split_at:]]
    else:
        lines = [words]
    typed = TITLE_START_S + TITLE_WORD_S * len(words)
    end = min(duration - 0.2, typed + TITLE_HOLD_S)
    if end <= TITLE_START_S:
        return None
    pieces, n = [], 0
    for line_no, line in enumerate(lines):
        for word in line:
            appear = int((TITLE_WORD_S * n) * 1000)
            pieces.append(
                "{\\alpha&HFF&\\fscx130\\fscy130"
                f"\\t({appear},{appear + 160},\\alpha&H00&\\fscx100\\fscy100)}}"
                f"{_ass_text(word)} "
            )
            n += 1
        if line_no < len(lines) - 1:
            pieces.append("\\N")

    def clock(t: float) -> str:
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

    fade_ms = int(TITLE_FADE_S * 1000)
    body = "".join(pieces).rstrip()
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, "
        "Encoding\n"
        # White, a warm yellow glow (the outline, blurred), no box.
        "Style: Title,Montserrat,120,&H00FFFFFF,&H00FFFFFF,&H0000C8FF,&H00000000,"
        "-1,-1,0,0,100,100,2,0,1,7,0,8,70,70,250,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,{clock(TITLE_START_S)},{clock(end)},Title,,0,0,0,,"
        f"{{\\blur6\\fad(0,{fade_ms})}}{body}\n",
        encoding="utf-8",
    )
    return path


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_edit(
    plan: EditPlan,
    music: Path,
    output: Path,
    work: Path,
    ffmpeg: str = "ffmpeg",
    title: str = "",
) -> Path:
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
    # Picture and music come up together out of black and silence, and go
    # out together at the end over a longer stretch — so the edit starts and
    # finishes rather than switching on and off, and loops cleanly where it
    # is played on repeat. The title is drawn after the fades, so it glows
    # over the dark opening instead of rising with it. The video is
    # re-encoded for it; the cuts were joined by stream copy, and a fade
    # cannot be.
    fade_s = min(FADE_OUT_S, plan.duration / 4)
    fade_at = max(0.0, plan.duration - fade_s)
    fade_in = min(FADE_IN_S, plan.duration / 6)
    titled = title_ass(title, work / "title.ass", plan.duration) if title.strip() else None
    overlay = (
        f",ass='{_filter_path(titled)}':fontsdir='{_filter_path(FONTS_DIR)}'" if titled else ""
    )
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(joined), "-ss",
         f"{plan.music_start:.3f}", "-t", f"{plan.duration:.3f}", "-i", str(music),
         "-filter_complex",
         f"[0:v]fade=t=in:st=0:d={fade_in:.3f}:color=black,"
         f"fade=t=out:st={fade_at:.3f}:d={fade_s:.3f}:color=black{overlay}[v];"
         f"[1:a]afade=t=in:st=0:d={fade_in:.3f},"
         f"afade=t=out:st={fade_at:.3f}:d={fade_s:.3f}[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(output)],
        check=True,
    )
    return output
