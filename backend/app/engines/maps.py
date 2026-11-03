"""Glowing map shots for "what if?" videos about places.

Image models cannot draw geography — a border comes back invented — so a
map is drawn here, from Natural Earth's 1:50m country outlines (public
domain, assets/geo/countries.json, built by scripts/build_geo.py): a dark
night-blue world, the neighbours as dim outlines, the subject lit in gold
with a soft glow, and a slow push in. Two moves on top of that:

- "vanish": the subject flickers and goes out, leaving the hole;
- places named by the script are marked with a pulsing dot and a label.

Drawn once at an oversize and then moved with the same affine warp as the
Ken Burns path, so a shot costs about as much as a still.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_ROOT

GEO = BACKEND_ROOT / "app" / "assets" / "geo" / "countries.json"
FONT = BACKEND_ROOT / "app" / "assets" / "fonts" / "Montserrat-Bold.ttf"

# BGR
_BG_TOP = (10, 5, 2)
_BG_BOTTOM = (22, 11, 5)
_LAND = (58, 38, 24)
_EDGE = (80, 140, 190)
_GOLD = (70, 190, 255)
_GOLD_FILL = (40, 110, 160)

_OVERSIZE = 1.3


@dataclass
class Place:
    name: str
    lat: float
    lon: float


@dataclass
class MapShot:
    focus: list[str]  # ADM0_A3 codes of the subject
    action: str = "glow"  # glow | vanish | mark
    places: list[Place] = field(default_factory=list)
    # Already vanished in an earlier scene: drawn as the hole it left, so
    # a later "mark" does not bring the country back.
    gone: bool = False


def available() -> bool:
    """OpenCV (requirements-vision) and the outlines are both here."""
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return GEO.is_file()


def shot_for(spec, gone: bool = False) -> MapShot:
    """A schemas.project.MapSpec as a MapShot."""
    return MapShot(
        focus=list(spec.focus),
        action=spec.action,
        places=[Place(p.name, p.lat, p.lon) for p in spec.places],
        gone=gone,
    )


def vanished_before(scenes, index: int) -> bool:
    """Whether a scene's countries already went out earlier in the video."""
    here = scenes[index].map
    if not here:
        return False
    return any(
        s.map and s.map.action == "vanish" and set(s.map.focus) & set(here.focus)
        for s in scenes[:index]
    )


@lru_cache(maxsize=1)
def _countries() -> list[dict]:
    return json.loads(GEO.read_text(encoding="utf-8"))


def find_country(name_or_code: str) -> str | None:
    """An ADM0_A3 code for a code or a name in any of the stored languages."""
    key = name_or_code.strip().casefold()
    for c in _countries():
        if key in {
            str(c.get(k) or "").casefold() for k in ("a3", "iso", "en", "tr", "pl", "de")
        }:
            return c["a3"]
    return None


def _merc(lon: float, lat: float) -> tuple[float, float]:
    lat = max(min(lat, 84.0), -84.0)
    return lon, math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def _bounds(codes: list[str]) -> tuple[float, float, float, float] | None:
    xs, ys = [], []
    for c in _countries():
        if c["a3"] in codes:
            for ring in c["rings"]:
                for lon, lat in ring:
                    x, y = _merc(lon, lat)
                    xs.append(x)
                    ys.append(y)
    if not xs:
        return None
    # Overseas specks (French Guiana for France, Alaska for the US) would
    # zoom the camera out to half the planet; keep the bulk of the points.
    xs.sort()
    ys.sort()
    lo, hi = int(len(xs) * 0.03), int(len(xs) * 0.97) - 1
    return xs[lo], ys[lo], xs[hi], ys[hi]


def _layers(shot: MapShot, width: int, height: int):
    """(lit, dark) images at the oversize, and the projection used."""
    import cv2
    import numpy as np

    big_w, big_h = round(width * _OVERSIZE), round(height * _OVERSIZE)
    box = _bounds(shot.focus) or (-10.0, 30.0, 40.0, 60.0)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    span_x, span_y = max(box[2] - box[0], 1.0), max(box[3] - box[1], 1.0)
    # The subject fills about three quarters of the frame's width.
    scale = min(width * 0.78 / span_x, height * 0.45 / span_y)

    def project(lon: float, lat: float) -> tuple[float, float]:
        x, y = _merc(lon, lat)
        return big_w / 2 + (x - cx) * scale, big_h / 2 - (y - cy) * scale

    grad = np.linspace(0, 1, big_h, dtype=np.float32)[:, None, None]
    bg = (np.array(_BG_TOP) * (1 - grad) + np.array(_BG_BOTTOM) * grad).astype(np.float32)
    bg = np.repeat(bg, big_w, axis=1)
    rng = np.random.default_rng(7)
    for _ in range(900):
        x, y = rng.integers(0, big_w), rng.integers(0, big_h)
        bg[y, x] = (200, 200, 220) if rng.random() < 0.3 else (120, 110, 110)
    base = bg.astype(np.uint8)

    subject_mask = np.zeros((big_h, big_w), np.uint8)
    edges = np.zeros((big_h, big_w), np.uint8)
    land = base.copy()
    for c in _countries():
        polys = []
        for ring in c["rings"]:
            pts = np.array([project(lon, lat) for lon, lat in ring], dtype=np.float32)
            if (pts[:, 0].max() < -big_w or pts[:, 0].min() > 2 * big_w
                    or pts[:, 1].max() < -big_h or pts[:, 1].min() > 2 * big_h):
                continue
            polys.append(pts.astype(np.int32))
        if not polys:
            continue
        if c["a3"] in shot.focus:
            cv2.fillPoly(subject_mask, polys, 255, lineType=cv2.LINE_AA)
        cv2.fillPoly(land, polys, _LAND, lineType=cv2.LINE_AA)
        cv2.polylines(edges, polys, True, 255, 2, lineType=cv2.LINE_AA)
    # Every border faintly lit in gold, the subject brightly: the look of
    # the night maps these videos use.
    dark: Any = land.astype(np.float32)
    soft = cv2.GaussianBlur(edges.astype(np.float32), (0, 0), 6)[..., None] / 255.0
    dark += soft * np.array(_EDGE, np.float32) * 0.5
    dark[edges > 0] = dark[edges > 0] * 0.4 + np.array(_EDGE, np.float32) * 0.6
    dark = np.clip(dark, 0, 255).astype(np.uint8)

    # The subject: a warm fill, a bright edge and two glows (wide, tight).
    lit: Any = dark.astype(np.float32)
    m = (subject_mask / 255.0)[..., None]
    lit = lit * (1 - m * 0.6) + np.array(_GOLD_FILL, np.float32) * m * 0.6
    outline = cv2.morphologyEx(subject_mask, cv2.MORPH_GRADIENT, np.ones((5, 5), np.uint8))
    for sigma, gain in ((28, 0.9), (8, 1.2)):
        glow = cv2.GaussianBlur(outline.astype(np.float32), (0, 0), sigma)[..., None] / 255.0
        lit += glow * np.array(_GOLD, np.float32) * gain
    lit[outline > 0] = _GOLD
    hole: Any = dark.astype(np.float32)
    # Where it was: the land gone dark, a faint ghost of the coast left.
    hole = hole * (1 - m) + np.array(_BG_BOTTOM, np.float32) * m
    ghost = cv2.GaussianBlur(outline.astype(np.float32), (0, 0), 3)[..., None] / 255.0
    hole += ghost * np.array(_EDGE, np.float32) * 0.5
    return np.clip(lit, 0, 255).astype(np.uint8), np.clip(hole, 0, 255).astype(np.uint8), project


def frames(shot: MapShot, width: int, height: int, fps: int, total_frames: int, label_font=None):
    """BGR frames of the shot."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    lit, hole, project = _layers(shot, width, height)
    big_h, big_w = lit.shape[:2]
    font = label_font or ImageFont.truetype(str(FONT), 42)
    marks = [(p, project(p.lon, p.lat)) for p in shot.places[:4]]
    # Labels of places close together (the two straits) would sit on each
    # other: each one that would is pushed below the one before.
    label_dy: list[float] = []
    for i, (_, (bx, by)) in enumerate(marks):
        dy = 0.0
        for j in range(i):
            ox, oy = marks[j][1]
            if abs(bx - ox) < 420 and abs((by + dy) - (oy + label_dy[j])) < 56:
                dy = (oy + label_dy[j]) - by + 58
        label_dy.append(dy)
    for k in range(total_frames):
        t = k / fps
        f = k / max(total_frames - 1, 1)
        if shot.gone:
            frame = hole
        elif shot.action == "vanish":
            # Lit, a flicker, then out — over the first second and a half.
            gone = min(max((t - 0.5) / 1.0, 0.0), 1.0)
            flicker = 0.5 + 0.5 * math.sin(t * 38) if 0.5 < t < 1.5 else 1.0
            mix = (1 - gone) * flicker
            frame = cv2.addWeighted(lit, mix, hole, 1 - mix, 0)
        else:
            frame = lit
        # A slow push in on the centre.
        z = (1 / _OVERSIZE) * (1.0 + 0.10 * f)
        x0 = (big_w - width / z) / 2
        y0 = (big_h - height / z) / 2
        m = np.array([[z, 0, -x0 * z], [0, z, -y0 * z]], dtype=np.float32)
        out = cv2.warpAffine(frame, m, (width, height), flags=cv2.INTER_LINEAR)
        if marks:
            img = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img, "RGBA")
            for i, (place, (bx, by)) in enumerate(marks):
                appear = min(max((t - 0.3 - i * 0.35) / 0.3, 0.0), 1.0)
                if appear <= 0:
                    continue
                x, y = (bx - x0) * z, (by - y0) * z
                pulse = (t * 1.4 + i * 0.3) % 1.0
                r = 10 + 34 * pulse
                a = int(200 * (1 - pulse) * appear)
                draw.ellipse((x - r, y - r, x + r, y + r), outline=(255, 190, 70, a), width=4)
                draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(255, 205, 90, int(255 * appear)))
                text = place.name.upper()
                tw = draw.textlength(text, font=font)
                tx = min(max(x + 18, 20), width - tw - 20)
                draw.text(
                    (tx, y - 26 + label_dy[i] * z), text, font=font, fill=(255, 255, 255, int(255 * appear)),
                    stroke_width=4, stroke_fill=(0, 0, 0, int(200 * appear)),
                )
            out = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        yield out


def render_clip(shot: MapShot, output: Path, width: int, height: int, fps: int, seconds: float,
                ffmpeg: str = "ffmpeg") -> Path:
    """The shot as a silent MP4, long enough for any scene it is used in."""
    total = max(1, round(seconds * fps))
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(output),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for frame in frames(shot, width, height, fps, total):
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
    err = proc.stderr.read() if proc.stderr else b""
    if proc.wait() != 0:
        raise RuntimeError(err.decode(errors="ignore"))
    return output
