"""Info graphics for fact-driven videos ("what if?"): a running list of what
the viewer just learned, a counter, and stamps on the big moments.

Drawn as ASS events in the caption file rather than as a separate ffmpeg
pass — libass already burns the captions, so the graphics cost nothing in
render time and survive an edit's re-burn (services/editing.py rebuilds
them from the stored script). The data comes from the script itself: the
model that writes a line also names its list label, icon and stamp, so the
graphics always describe what is being said.

Sound effects for the same moments are mixed into each scene's voice track
(`mix_scene_sfx`) — before the clips are cut, so they too survive an edit.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.schemas.project import GraphicCounter, Scene, SceneGraphic

# Icons the script may name, drawn from the monochrome Noto Emoji font
# (assets/fonts, OFL) in the caption highlight colour. A fixed list, so the
# model picks a word rather than a glyph and nothing unrenderable arrives.
ICONS: dict[str, str] = {
    "apple": "🍎", "fruit": "🍇", "vegetable": "🥕", "chicken": "🍗", "meat": "🍖",
    "fish": "🐟", "bread": "🍞", "wheat": "🌾", "cheese": "🧀", "chocolate": "🍫",
    "sweets": "🍬", "coffee": "☕", "tea": "🍵", "drink": "🥤", "wine": "🍷",
    "plane": "✈", "train": "🚆", "ship": "🚢", "car": "🚗", "truck": "🚚",
    "road": "🛣", "port": "⚓", "factory": "🏭", "mine": "⛏", "oil": "🛢",
    "energy": "⚡", "money": "💰", "phone": "📱", "computer": "💻", "game": "🎮",
    "film": "🎬", "music": "🎵", "book": "📖", "furniture": "🛋", "house": "🏠",
    "city": "🏙", "tree": "🌳", "forest": "🌲", "flower": "🌷", "animal": "🐾",
    "bird": "🐦", "insect": "🐝", "water": "💧", "sea": "🌊", "mountain": "⛰",
    "sun": "☀", "moon": "🌙", "star": "⭐", "fire": "🔥", "snow": "❄",
    "gem": "💎", "sport": "⚽", "science": "🔬", "medicine": "💊", "clothes": "👕",
    "gift": "🎁", "clock": "⏰", "people": "👥", "language": "💬", "art": "🎨",
    "nut": "🌰", "bridge": "🌉", "pipeline": "🛢", "rocket": "🚀", "ice": "🧊",
}

ICON_FONT = "Noto Emoji"

# The list stops growing here: past eight rows it reaches the captions.
MAX_ROWS = 8


@dataclass
class Plan:
    """What a render draws besides captions."""

    counter: GraphicCounter | None = None
    title: str | None = None
    tag: str | None = None


def enabled(config) -> bool:
    """Whether a project draws info graphics: as asked, or by its format —
    "what if?" writes the data for them, a free topic does not."""
    if config.info_graphics is not None:
        return bool(config.info_graphics)
    return str(config.script_format) in ("what_if", "outbreak")


def plan_for(project) -> Plan | None:
    """The graphics a finished project draws, from its stored script; None
    when it draws none."""
    return plan_from(project.config, project.script)


def plan_from(config, script) -> Plan | None:
    if not script or not enabled(config):
        return None
    if not (script.counter or any(s.graphic for s in script.scenes)):
        return None
    language = str(getattr(config, "language", "en"))
    if str(getattr(config, "script_format", "")) == "outbreak":
        tag = _SERIES_TAG.get(language, _SERIES_TAG["en"]).format(n=script.episode)
    else:
        tag = _TAG.get(language, _TAG["en"])
    return Plan(counter=script.counter, title=script.tally_title, tag=tag)


# The same label on a series, with the episode.
_SERIES_TAG = {
    "tr": "KURGU · BÖLÜM {n}", "en": "FICTION · EPISODE {n}", "pl": "FIKCJA · ODCINEK {n}",
    "de": "FIKTION · FOLGE {n}", "es": "FICCIÓN · EPISODIO {n}", "fr": "FICTION · ÉPISODE {n}",
    "pt": "FICÇÃO · EPISÓDIO {n}", "it": "FINZIONE · EPISODIO {n}", "ru": "ВЫМЫСЕЛ · СЕРИЯ {n}",
}

# The honesty label in the corner of every "what if?" video.
_TAG = {
    "tr": "KURGUSAL SENARYO", "en": "HYPOTHETICAL", "pl": "SCENARIUSZ FIKCYJNY",
    "de": "FIKTIVES SZENARIO", "es": "ESCENARIO FICTICIO", "fr": "SCÉNARIO FICTIF",
    "pt": "CENÁRIO FICTÍCIO", "it": "SCENARIO IPOTETICO", "ru": "ВЫМЫШЛЕННЫЙ СЦЕНАРИЙ",
}


def ass_extras(
    scenes: list[Scene], plan: Plan, style, language: str, play_res: tuple[int, int]
) -> tuple[list[str], list[str]]:
    """(style lines, event lines) for the caption file."""
    from app.engines.subtitle_engine import font_for

    font = font_for(style.font_family, language)
    return (
        styles(font, style.highlight_color),
        events(scenes, plan, style.highlight_color, language, font, play_res),
    )


def _ts(ms: int) -> str:
    ms = max(0, ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, rem = divmod(rem, 1000)
    return f"{h}:{m:02d}:{s:02d}.{rem // 10:02d}"


def _clean(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\\", "").replace("\n", " ").strip()


def _number(value: int, language: str) -> str:
    """Thousands grouped the way the viewer writes them."""
    grouped = f"{value:,}"
    if language in ("tr", "de", "it", "es", "pt", "id"):
        return grouped.replace(",", ".")
    if language in ("pl", "fr", "ru"):
        return grouped.replace(",", " ")
    return grouped


def _upper(text: str, language: str) -> str:
    if language == "tr":
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


def styles(text_font: str, highlight: str) -> list[str]:
    """ASS style lines the graphic events use, added to the caption header.

    Stamp is a box (BorderStyle 3) in the caption highlight colour with dark
    text — the same colour the active word lights up in, so the two read as
    one design."""
    # List and counter sit on translucent dark boxes (BorderStyle 3, the
    # outline colour at 0x60 alpha): bright footage behind them otherwise
    # swallows white text, which is how the reference videos do it too.
    return [
        f"Style: GfxList,{text_font},52,&H00FFFFFF,&H000000FF,&H60000000,&H00000000,"
        "-1,0,0,0,100,100,0,0,3,12,0,7,60,60,0,1",
        f"Style: GfxCounter,{text_font},38,&H00FFFFFF,&H000000FF,&H60000000,&H00000000,"
        "-1,0,0,0,100,100,1,0,3,12,0,7,60,60,0,1",
        f"Style: GfxStamp,{text_font},84,&H00101010,&H000000FF,{highlight},&H00000000,"
        "-1,0,0,0,100,100,1,0,3,18,0,5,60,60,0,1",
        # Chapter headlines: drawn twice, a blurred glow in the highlight
        # under a crisp copy — the lit look of the reference videos.
        f"Style: GfxChapter,{text_font},104,{highlight},&H000000FF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,1,0,1,3,0,8,60,60,0,1",
        f"Style: GfxTag,{text_font},26,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,4,0,1,2,0,8,60,60,0,1",
    ]


def events(
    scenes: list[Scene],
    plan: Plan,
    highlight: str,
    language: str,
    text_font: str,
    play_res: tuple[int, int] = (1080, 1920),
) -> list[str]:
    """Dialogue lines for the counter, the list and the stamps, timed
    against the concatenated timeline (`scene_start_ms`)."""
    from app.engines.subtitle_engine import scene_start_ms

    if not scenes:
        return []
    sx, sy = play_res[0] / 1080, play_res[1] / 1920
    total = scene_start_ms(scenes, len(scenes))
    out: list[str] = []
    left = round(60 * sx)
    centre = round(540 * sx)
    chapters = any(s.graphic and s.graphic.chapter for s in scenes)
    # Headlines take the top centre, so the list starts below them.
    y = round((390 if chapters else 170) * sy)

    if plan.tag:
        out.append(
            f"Dialogue: 2,{_ts(0)},{_ts(total)},GfxTag,,0,0,0,,"
            f"{{\\pos({centre},{round(112 * sy)})\\alpha&H40&}}{_clean(plan.tag)[:32]}"
        )
    for index, scene in enumerate(scenes):
        g = scene.graphic
        if not (g and g.chapter):
            continue
        start = scene_start_ms(scenes, index)
        # Until the next headline or the end of this scene, whichever is later
        # in a beat of several scenes; at least the scene itself.
        nxt = next(
            (k for k in range(index + 1, len(scenes)) if (scenes[k].graphic or SceneGraphic()).chapter),
            len(scenes),
        )
        end = scene_start_ms(scenes, nxt)
        text = _upper(_clean(g.chapter)[:32], language)
        pos = f"\\pos({centre},{round(160 * sy)})"
        grow = "\\fscx118\\fscy118\\t(0,260,\\fscx100\\fscy100)\\fad(140,200)"
        out.append(
            f"Dialogue: 4,{_ts(start)},{_ts(end)},GfxChapter,,0,0,0,,"
            f"{{{pos}{grow}\\bord10\\3c{highlight}\\blur14\\alpha&H70&}}{text}"
        )
        out.append(
            f"Dialogue: 5,{_ts(start)},{_ts(end)},GfxChapter,,0,0,0,,{{{pos}{grow}}}{text}"
        )

    if plan.counter and plan.counter.label:
        c = plan.counter
        first = scene_start_ms(scenes, 1) if len(scenes) > 1 else 0
        # Where a map shows the country going out, the count runs with it —
        # later behind an identity card, which goes out once it is read
        # (maps.frames), or the card's population sits beside a zero.
        vanish = next(
            (i for i, s in enumerate(scenes) if s.map and s.map.action == "vanish"), None
        )
        spread = next(
            (i for i, s in enumerate(scenes) if s.map and s.map.action == "spread"), None
        )
        if vanish is not None:
            first = scene_start_ms(scenes, vanish) + (2300 if scenes[vanish].card else 500)
        elif spread is not None:
            # An outbreak's count climbs as the red first spreads.
            first = scene_start_ms(scenes, spread) + 300
        label = _clean(c.label)[:28]
        out.append(
            f"Dialogue: 2,{_ts(0)},{_ts(total)},GfxCounter,,0,0,0,,"
            f"{{\\pos({left},{y})\\fad(200,0)}}{label}"
        )
        # Holds the start until the first consequence lands, counts to the
        # end over a second and a half, then holds the end in the highlight.
        steps, run_ms = 24, 1500
        num_y = y + round(58 * sy)
        segments = [(0, first, c.start, False)]
        for k in range(1, steps):
            value = round(c.start + (c.end - c.start) * k / steps)
            segments.append((first + run_ms * (k - 1) // steps, first + run_ms * k // steps, value, False))
        segments.append((first + run_ms * (steps - 1) // steps, total, c.end, True))
        for start, end, value, final in segments:
            if end <= start:
                continue
            colour = highlight if final else "&H00FFFFFF"
            out.append(
                f"Dialogue: 2,{_ts(start)},{_ts(end)},GfxCounter,,0,0,0,,"
                f"{{\\pos({left},{num_y})\\fs{round(84 * sy)}\\c{colour}}}{_number(value, language)}"
            )
        y = num_y + round(130 * sy)

    if plan.title:
        out.append(
            f"Dialogue: 2,{_ts(scene_start_ms(scenes, 1) if len(scenes) > 1 else 0)},{_ts(total)},"
            f"GfxList,,0,0,0,,{{\\pos({left},{y})\\fs{round(38 * sy)}\\c{highlight}\\fad(250,0)}}"
            f"{_upper(_clean(plan.title)[:32], language)}"
        )
        y += round(70 * sy)

    row = round(84 * sy)
    rows = 0
    for index, scene in enumerate(scenes):
        g = scene.graphic
        start = scene_start_ms(scenes, index)
        if g and g.tally and rows < MAX_ROWS:
            icon = ICONS.get((g.icon or "").strip().lower(), "•")
            ry = y + rows * row
            text = _clean(g.tally)[:30]
            out.append(
                f"Dialogue: 2,{_ts(start + 80)},{_ts(total)},GfxList,,0,0,0,,"
                f"{{\\move({left - round(40 * sx)},{ry},{left},{ry},0,200)\\fad(180,0)}}"
                f"{{\\fn{ICON_FONT}\\c{highlight}}}{icon}{{\\fn{text_font}\\c&H00FFFFFF&}} {text}"
            )
            rows += 1
        if g and g.stamp:
            stamp = _upper(_clean(g.stamp)[:18], language)
            out.append(
                f"Dialogue: 3,{_ts(start + 250)},{_ts(start + 1500)},GfxStamp,,0,0,0,,"
                f"{{\\pos({round(540 * sx)},{round(1010 * sy)})\\frz-6"
                f"\\fscx170\\fscy170\\t(0,160,\\fscx100\\fscy100)\\fad(60,220)}}{stamp}"
            )
    return out


# ---------------------------------------------------------------------------
# Sound effects
# ---------------------------------------------------------------------------

# Synthesised, not sampled: no licence to track, and two short sounds are
# all this needs. A soft tick when a row joins the list; a filtered-noise
# whoosh under a stamp.
_POP = "sine=frequency=1320:duration=0.09,afade=t=out:st=0.01:d=0.08,volume=0.28"
_WHOOSH = (
    "anoisesrc=duration=0.5:color=pink:amplitude=0.9,highpass=f=500,lowpass=f=4000,"
    "afade=t=in:st=0:d=0.28,afade=t=out:st=0.3:d=0.2,volume=0.30"
)


async def _render_sound(spec: str, path: Path, ffmpeg: str) -> Path:
    if not path.exists():
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", spec,
            "-ar", "48000", "-ac", "1", str(path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="ignore"))
    return path


async def mix_scene_sfx(scene: Scene, work_dir: Path, ffmpeg: str = "ffmpeg") -> Path | None:
    """The scene's voice with its effects laid over the start: a tick for a
    new list row, a whoosh for a stamp. None when the scene has neither, or
    the mix fails — the plain voice is always a fine fallback."""
    g = scene.graphic
    voice = scene.audio.audio_path
    if not g or not voice or not (g.tally or g.stamp):
        return None
    try:
        layers: list[tuple[Path, int]] = []
        if g.tally:
            layers.append((await _render_sound(_POP, work_dir / "sfx_pop.wav", ffmpeg), 40))
        if g.stamp:
            layers.append((await _render_sound(_WHOOSH, work_dir / "sfx_whoosh.wav", ffmpeg), 120))
        out = work_dir / f"scene_{scene.index:02d}_sfx.wav"
        inputs = ["-i", str(voice)]
        chain = ""
        for k, (path, delay) in enumerate(layers, start=1):
            inputs += ["-i", str(path)]
            chain += f"[{k}:a]adelay={delay}|{delay}[s{k}];"
        mix = "".join(f"[s{k}]" for k in range(1, len(layers) + 1))
        chain += f"[0:a]{mix}amix=inputs={len(layers) + 1}:duration=first:normalize=0[a]"
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *inputs,
            "-filter_complex", chain, "-map", "[a]", "-ar", "48000", "-ac", "1", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="ignore"))
        return out
    except Exception:  # noqa: BLE001 - effects are garnish
        import logging

        logging.getLogger(__name__).warning("Scene %s sound effects failed", scene.index, exc_info=True)
        return None
