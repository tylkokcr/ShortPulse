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
from app.engines.subtitle_engine import _uppercase

GEO = BACKEND_ROOT / "app" / "assets" / "geo" / "countries.json"
# Population, area and capital per country (scripts/build_country_facts.py).
FACTS = BACKEND_ROOT / "app" / "assets" / "geo" / "facts.json"
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
    # An identity card under the map: (title, [(label, value), ...]). The
    # country moves up to make room; with no country it is drawn over the
    # night sky alone (a card for the Moon).
    card: tuple[str, list[tuple[str, str]]] | None = None
    # For upper-casing labels: Turkish "i" is "İ" in capitals.
    language: str = "en"


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


def card_shot(scenes, index: int, card) -> MapShot:
    """The shot for a scene that shows the script's IdCard: its own map if
    it has one, else the country the video's maps are about, else none."""
    scene = scenes[index]
    if scene.map:
        shot = shot_for(scene.map, gone=vanished_before(scenes, index))
    else:
        focus = next((list(s.map.focus) for s in scenes if s.map and s.map.focus), [])
        gone = any(
            s.map and s.map.action == "vanish" and set(s.map.focus) & set(focus)
            for s in scenes[:index]
        )
        shot = MapShot(focus=focus, gone=gone)
    shot.card = (card.title, [(r.label, r.value) for r in card.rows])
    return shot


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


@lru_cache(maxsize=1)
def _facts() -> dict[str, dict]:
    return json.loads(FACTS.read_text(encoding="utf-8")) if FACTS.is_file() else {}


# The card's labels, and the counter's, in the languages the outlines are
# named in. Another language keeps the card the script wrote.
_CARD_LABELS = {
    "en": ("Capital", "Population", "Area", "Known for"),
    "tr": ("Başkent", "Nüfus", "Yüzölçümü", "Bilinen"),
    "pl": ("Stolica", "Ludność", "Powierzchnia", "Słynie z"),
    "de": ("Hauptstadt", "Einwohner", "Fläche", "Bekannt für"),
}
_POPULATION_OF = {
    "en": "Population of {name}",
    "tr": "{name} nüfusu",
    "pl": "Ludność: {name}",
    "de": "Einwohner: {name}",
}
# million, billion, thousand; decimal and thousands separators.
_UNITS = {
    "en": ("million", "billion", "", ".", ","),
    "tr": ("milyon", "milyar", "bin", ",", "."),
    "pl": ("mln", "mld", "tys.", ",", "\u00a0"),
    "de": ("Mio.", "Mrd.", "", ",", "."),
}


# A vanished country's video ends on the same question, so the next one
# is a series: the Italy script closed on "what would you miss first?"
# with its rules saying otherwise.
NEXT_COUNTRY = {
    "en": "Which country should vanish next? Tell me below.",
    "tr": "Sıradaki hangi ülke kaybolsun? Yorumlara yaz.",
    "pl": "Który kraj ma zniknąć następny? Napisz w komentarzu.",
    "de": "Welches Land soll als Nächstes verschwinden? Schreib es in die Kommentare.",
}


def _grouped(n: int, sep: str) -> str:
    return f"{n:,}".replace(",", sep)


def _population_text(n: int, language: str) -> str:
    million, billion, thousand, dot, sep = _UNITS[language]
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}".replace(".", dot) + f" {billion}"
    if n >= 10_000_000:
        return f"{round(n / 1e6)} {million}"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}".replace(".", dot) + f" {million}"
    rounded = round(n, -3)
    return f"{rounded // 1000} {thousand}" if thousand else _grouped(rounded, sep)


def _area_text(km2: int, language: str) -> str:
    # Two significant figures: computed from the outlines, it is within a
    # percent or two of the official figure, not exact.
    digits = len(str(int(km2)))
    return f"{_grouped(int(round(km2, 2 - digits)), _UNITS[language][4])} km²"


def country_name(code: str, language: str) -> str | None:
    country = next((c for c in _countries() if c["a3"] == code), None)
    if not country:
        return None
    return country.get(language) or country.get("en")


def country_card(
    code: str, language: str, known_for: str | None = None
) -> tuple[str, list[tuple[str, str]]] | None:
    """A country's identity card from the facts file, labelled in the
    script's language: (title, [(label, value), ...]). None for a language
    without labels or a country without facts."""
    facts = _facts().get(code)
    name = country_name(code, language)
    if language not in _CARD_LABELS or not facts or not name:
        return None
    capital_l, population_l, area_l, known_l = _CARD_LABELS[language]
    rows = []
    if facts.get("capital"):
        rows.append((capital_l, facts["capital"].get(language) or facts["capital"]["en"]))
    if facts.get("population"):
        rows.append((population_l, _population_text(int(facts["population"]), language)))
    if facts.get("area_km2"):
        rows.append((area_l, _area_text(int(facts["area_km2"]), language)))
    if known_for:
        rows.append((known_l, known_for))
    return (name, rows) if len(rows) >= 2 else None


def population_counter(code: str, language: str) -> tuple[str, int] | None:
    """(label, population) for the counter of a vanished country."""
    facts = _facts().get(code)
    name = country_name(code, language)
    if language not in _POPULATION_OF or not facts or not facts.get("population") or not name:
        return None
    return _POPULATION_OF[language].format(name=name), round(int(facts["population"]), -5)


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
    # The subject fills about three quarters of the frame's width — or,
    # above a card, the upper part of the frame.
    if shot.card:
        scale = min(width * 0.62 / span_x, height * 0.24 / span_y)
        centre_y = big_h / 2 - height * 0.17
    else:
        scale = min(width * 0.78 / span_x, height * 0.45 / span_y)
        centre_y = big_h / 2

    def project(lon: float, lat: float) -> tuple[float, float]:
        x, y = _merc(lon, lat)
        return big_w / 2 + (x - cx) * scale, centre_y - (y - cy) * scale

    grad = np.linspace(0, 1, big_h, dtype=np.float32)[:, None, None]
    bg = (np.array(_BG_TOP) * (1 - grad) + np.array(_BG_BOTTOM) * grad).astype(np.float32)
    bg = np.repeat(bg, big_w, axis=1)
    rng = np.random.default_rng(7)
    for _ in range(900):
        x, y = rng.integers(0, big_w), rng.integers(0, big_h)
        bg[y, x] = (200, 200, 220) if rng.random() < 0.3 else (120, 110, 110)
    base = bg.astype(np.uint8)

    if shot.card and not shot.focus:
        # A card about no country: the night sky alone.
        return base, base, project, base, None

    subject_mask = np.zeros((big_h, big_w), np.uint8)
    land_mask = np.zeros((big_h, big_w), np.uint8)
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
        cv2.fillPoly(land_mask, polys, 255)
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
    return (
        np.clip(lit, 0, 255).astype(np.uint8),
        np.clip(hole, 0, 255).astype(np.uint8),
        project,
        dark,
        land_mask,
    )


def frames(shot: MapShot, width: int, height: int, fps: int, total_frames: int, label_font=None):
    """BGR frames of the shot."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    lit, hole, project, dark, land_mask = _layers(shot, width, height)
    spread = shot.action == "spread" and not shot.gone
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
        elif spread:
            # An outbreak: the country unlit, the infection drawn on top.
            frame = dark
        elif shot.action == "vanish":
            # Lit, a flicker, then out — over the first second and a half;
            # behind a card, once the card has been read.
            tv = t - (1.8 if shot.card else 0.0)
            gone = min(max((tv - 0.5) / 1.0, 0.0), 1.0)
            flicker = 0.5 + 0.5 * math.sin(tv * 38) if 0.5 < tv < 1.5 else 1.0
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
        if spread and land_mask is not None:
            out = _infection(out, land_mask, m, marks, x0, y0, z, t, width, height)
        if shot.card:
            out = _draw_card(out, shot.card, t, width, height, shot.language)
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
                ring, dot = ((255, 70, 55), (255, 95, 80)) if spread else ((255, 190, 70), (255, 205, 90))
                draw.ellipse((x - r, y - r, x + r, y + r), outline=(*ring, a), width=4)
                draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(*dot, int(255 * appear)))
                text = _uppercase(place.name, shot.language)
                tw = draw.textlength(text, font=font)
                tx = min(max(x + 18, 20), width - tw - 20)
                draw.text(
                    (tx, y - 26 + label_dy[i] * z), text, font=font, fill=(255, 255, 255, int(255 * appear)),
                    stroke_width=4, stroke_fill=(0, 0, 0, int(200 * appear)),
                )
            out = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        yield out


# BGR: the infection's glow.
_RED = (40, 50, 235)


def _infection(out, land_mask, m, marks, x0: float, y0: float, z: float, t: float,
               width: int, height: int):
    """An outbreak spreading over the land from each marked place in turn —
    the first is where it started — as a red glow that grows and pulses,
    kept off the sea. Computed at a quarter of the size: it is a blur."""
    import cv2
    import numpy as np

    q = 4
    sw, sh = width // q, height // q
    land = cv2.resize(
        cv2.warpAffine(land_mask, m, (width, height), flags=cv2.INTER_NEAREST), (sw, sh)
    ).astype(np.float32) / 255.0
    ys, xs = np.mgrid[0:sh, 0:sw].astype(np.float32)
    heat = np.zeros((sh, sw), np.float32)
    for i, (_, (bx, by)) in enumerate(marks):
        grow = min(max((t - 0.3 - i * 0.6) / 2.5, 0.0), 1.0)
        if grow <= 0:
            continue
        reach = (0.24 if i == 0 else 0.13) * width * (1 - (1 - grow) ** 2) / q + 1.0
        x, y = (bx - x0) * z / q, (by - y0) * z / q
        # A fourth power: a solid core with a visible front, not a haze.
        d2 = ((xs - x) ** 2 + (ys - y) ** 2) / (reach * reach)
        heat += np.exp(-(d2 * d2))
    pulse = 0.85 + 0.15 * math.sin(t * 5.0)
    heat = np.clip(heat, 0.0, 1.0) * land * pulse
    big = cv2.resize(heat, (width, height), interpolation=cv2.INTER_LINEAR)[..., None]
    lit = out.astype(np.float32) * (1 - big * 0.35) + big * np.array(_RED, np.float32) * 0.95
    return np.clip(lit, 0, 255).astype(np.uint8)


def _draw_card(frame, card, t: float, width: int, height: int, language: str = "en"):
    """The identity card over a BGR frame at time t: a dark glass panel
    with a gold edge rises into place, then its rows come in one by one."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    title, rows = card
    u = width / 1080
    rise = min(max((t - 0.25) / 0.45, 0.0), 1.0)
    if rise <= 0:
        return frame
    ease = 1 - (1 - rise) ** 3
    title_font = ImageFont.truetype(str(FONT), round(64 * u))
    label_font = ImageFont.truetype(str(FONT), round(34 * u))
    value_font = ImageFont.truetype(str(FONT), round(44 * u))

    pad, row_h, title_h = round(44 * u), round(84 * u), round(108 * u)
    left, right = round(70 * u), width - round(70 * u)
    top = round(height * 0.47 + (1 - ease) * 80 * u)
    bottom = top + title_h + row_h * len(rows) + pad

    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = ease
    radius = round(30 * u)
    # The glow behind the edge, then the glass, then the edge itself.
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(
        (left, top, right, bottom), radius, outline=(255, 190, 70, int(150 * alpha)),
        width=round(10 * u),
    )
    glow_arr: Any = cv2.GaussianBlur(np.asarray(glow), (0, 0), 14 * u)
    layer = Image.alpha_composite(layer, Image.fromarray(glow_arr))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (left, top, right, bottom), radius, fill=(8, 12, 22, int(215 * alpha)),
        outline=(255, 200, 90, int(255 * alpha)), width=max(2, round(3 * u)),
    )
    draw.text(
        ((left + right) / 2, top + title_h / 2 + 4 * u), _uppercase(title, language), font=title_font,
        anchor="mm", fill=(255, 205, 90, int(255 * alpha)),
    )
    for i, (label, value) in enumerate(rows):
        shown = min(max((t - 0.7 - i * 0.28) / 0.25, 0.0), 1.0)
        if shown <= 0:
            continue
        y = top + title_h + row_h * i
        draw.line(
            (left + pad, y, right - pad, y), fill=(255, 255, 255, int(40 * shown)),
            width=max(1, round(2 * u)),
        )
        mid = y + row_h / 2
        dx = (1 - shown) * 30 * u
        draw.text(
            (left + pad + dx, mid), _uppercase(label, language), font=label_font, anchor="lm",
            fill=(255, 255, 255, int(150 * shown)),
        )
        # A long value steps down rather than running into its label.
        fit, size = value_font, 44
        room = right - left - 2 * pad - draw.textlength(_uppercase(label, language), font=label_font)
        while size > 26 and draw.textlength(value, font=fit) > room - 24 * u:
            size -= 4
            fit = ImageFont.truetype(str(FONT), round(size * u))
        draw.text(
            (right - pad + dx, mid), value, font=fit, anchor="rm",
            fill=(255, 255, 255, int(255 * shown)),
        )
    out = Image.alpha_composite(img, layer).convert("RGB")
    return cv2.cvtColor(np.asarray(out), cv2.COLOR_RGB2BGR)


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
