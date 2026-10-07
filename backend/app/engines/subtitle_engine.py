"""Generates dynamic, TikTok-style .ass subtitle files.

Words are grouped into short on-screen lines (default: up to 4 words).
Within each line, one Dialogue event is emitted per active word window, so
that as the voiceover plays, the currently-spoken word is rendered in the
highlight color and slightly scaled up ("pop") while the rest of the line
stays in the primary color — the classic caption style used across TikTok/
CapCut-style short-form video.

Output is a standard .ass file that FFmpeg burns in via the `ass` filter
in render_engine.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.schemas.project import Scene, SubtitleStyle, TextOverlay, Word
from app.services import profanity

logger = logging.getLogger(__name__)

# Which bundled font can draw which language.
#
# Not a preference — a capability, measured from each file's cmap rather
# than assumed from its Google Fonts listing. libass does not report a
# missing glyph; it draws an empty box and returns success, so a font
# asked for a script it does not have produces a finished video full of
# tofu and no error anywhere. That is exactly what Arabic did in
# production until this map existed: the language picker offered it, the
# render succeeded, and every caption came out as rectangles.
#
# The display faces are Latin-only by nature, so a project in Russian or
# Arabic falls back rather than being refused — the style is a
# preference, the alphabet is not.
_LATIN = frozenset({"en", "tr", "es", "fr", "de", "pt", "it"})
FONT_COVERAGE: dict[str, frozenset[str]] = {
    "Montserrat": _LATIN | {"ru"},
    "Anton": _LATIN,
    "Bangers": _LATIN,
    # No ğ/ş/ı, so Turkish is not in its Latin set despite the rest being.
    "Permanent Marker": _LATIN - {"tr"},
    # Latin as well as Arabic, which is not why it is here but is worth
    # recording accurately: this map is what each file *can* draw, not
    # what it is for. A test measures it against the files, and declaring
    # a narrower set than the truth is how that test earns its keep.
    "Noto Sans Arabic": _LATIN | {"ar"},
}

# Where a language goes when the chosen font cannot draw it. Montserrat
# covers everything the app offers except Arabic, which has no Latin face
# to fall back to at all.
_FALLBACK_BY_LANGUAGE = {"ar": "Noto Sans Arabic"}
_DEFAULT_FONT = "Montserrat"


def font_for(font_family: str, language: str) -> str:
    """The font that can actually draw this language, preferring the
    requested one.

    Silent substitution is the right answer here and a surprising one, so
    it is logged: a caption in the wrong face is a cosmetic
    disappointment, and a caption in empty boxes is an unusable video.
    """
    lang = (language or "en").lower()
    if lang in FONT_COVERAGE.get(font_family, frozenset()):
        return font_family

    substitute = _FALLBACK_BY_LANGUAGE.get(lang, _DEFAULT_FONT)
    if font_family:
        logger.info(
            "Captions in %r: %s cannot draw it, using %s", lang, font_family, substitute
        )
    return substitute

ASS_HEADER_TEMPLATE = """[Script Info]
Title: ShortPulse Auto Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{font_size},{primary_color},&H000000FF,{outline_color},&H00000000,-1,0,0,0,100,100,{spacing},0,{border_style},{outline_width},{shadow},{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_ALIGNMENT_BY_POSITION = {
    "bottom_third": 2,  # bottom-center
    "middle": 5,  # middle-center
    "top_third": 8,  # top-center
}
_MARGIN_V_BY_POSITION = {
    "bottom_third": 260,
    "middle": 0,
    "top_third": 260,
}


@dataclass
class SubtitleLine:
    words: list[Word]
    start_ms: int
    end_ms: int


def _format_timestamp(ms: int) -> str:
    ms = max(ms, 0)
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, centiseconds = divmod(rem, 1_000)
    centiseconds //= 10
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


# Words a caption line should not end on: articles, prepositions,
# conjunctions, the verb "to be". A line that stops on one of these reads
# as cut mid-thought ("THIS MODEL IS" / "SPECIALLY MADE"), so the break
# moves past it. Small on purpose — the common offenders, not a grammar.
_WEAK_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        "a an the of to in on at for from with by and or but is are was were be "
        "it its this that as so if than then into our your their my his her".split()
    ),
    "tr": frozenset("ve ile bir bu şu o da de ki ya ama için gibi çok en her".split()),
    "de": frozenset(
        "der die das den dem des ein eine einen einem und oder aber mit von zu im in "
        "an auf für ist sind war".split()
    ),
    "fr": frozenset(
        "le la les un une des de du et ou mais à au aux en dans sur pour par est "
        "sont ce cette".split()
    ),
    "es": frozenset(
        "el la los las un una unos unas de del y o pero a al en con por para es "
        "son este esta".split()
    ),
    "pt": frozenset(
        "o a os as um uma de do da dos das e ou mas em no na com por para é são "
        "este esta".split()
    ),
    "it": frozenset(
        "il lo la i gli le un una di del della e o ma a al in con per è sono questo "
        "questa".split()
    ),
    "ru": frozenset("и в во на с со к по из за о об от до а но что это как".split()),
}

_SENTENCE_END = (".", "!", "?", "…", "。", "！", "？")
_CLAUSE_END = (",", ";", ":", "、", "，")
# A silence this long between two words ends the line whatever the
# words are: a caption that waits on screen across a pause has gone stale.
_PAUSE_MS = 700


def _bare(text: str) -> str:
    return text.strip(".,!?;:…\"'“”«»()").lower()


def _ending_cost(last: Word, language: str) -> int:
    """What it costs to end a line (not the sentence) on `last`."""
    text = last.text.rstrip()
    if text.endswith(_CLAUSE_END):
        return -3
    weak = _WEAK_WORDS.get(language.split("-")[0].lower(), frozenset())
    return 12 if _bare(text) in weak else 0


def _plan_run(run: list[Word], max_per_line: int, language: str) -> list[list[Word]]:
    """Lines for one sentence (or one stretch between pauses).

    Every way of breaking the run is priced and the cheapest kept: a line
    costs something just for existing, more for being short ("4 + 1"
    leaves a lone word where "3 + 2" reads as two phrases), less for
    ending on a comma and a lot for ending on an article or preposition
    ("THANKS TO THE" / "REMOVABLE FUR COLLAR"). Pricing the whole run
    rather than nudging each break means a line can be added when the
    words will not otherwise divide well — three-word styles have no
    slack for a nudge, which is where the weak endings survived.
    """
    n = len(run)
    if n <= max_per_line:
        return [run]
    inf = float("inf")
    best = [inf] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for end in range(1, n + 1):
        for length in range(1, min(max_per_line, end) + 1):
            start = end - length
            if best[start] == inf:
                continue
            cost = 4 + (max_per_line - length) ** 2
            if length == 1:
                cost += 3
            if end < n:
                cost += _ending_cost(run[end - 1], language)
            if best[start] + cost < best[end]:
                best[end] = best[start] + cost
                back[end] = start
    lines: list[list[Word]] = []
    end = n
    while end > 0:
        start = back[end]
        lines.append(run[start:end])
        end = start
    return lines[::-1]


def plan_lines(words: list[Word], max_per_line: int, language: str = "en") -> list[list[Word]]:
    """Split a caption track into the lines it will be shown in.

    Words already marked `starts_line` are a plan someone made — the last
    render, or a person in the editor — and are kept as they are. Only a
    line that has grown past twice the limit (a long paste into one line)
    is split again, because a caption that runs off the frame is worse than
    one that moved. Without marks the lines are planned: sentences and
    pauses first, then even lines within each.
    """
    max_per_line = max(max_per_line, 1)
    if not words:
        return []

    if any(word.starts_line for word in words):
        marked: list[list[Word]] = []
        for word in words:
            if word.starts_line or not marked:
                marked.append([word])
            else:
                marked[-1].append(word)
        out: list[list[Word]] = []
        for line in marked:
            if len(line) > max_per_line * 2:
                out.extend(_plan_run(line, max_per_line, language))
            else:
                out.append(line)
        return out

    runs: list[list[Word]] = [[]]
    for i, word in enumerate(words):
        if runs[-1] and word.start_ms - words[i - 1].end_ms >= _PAUSE_MS:
            runs.append([])
        runs[-1].append(word)
        if word.text.rstrip().endswith(_SENTENCE_END):
            runs.append([])
    lines: list[list[Word]] = []
    for run in runs:
        if run:
            lines.extend(_plan_run(run, max_per_line, language))
    return lines


def with_line_starts(words: list[Word], max_per_line: int, language: str = "en") -> list[Word]:
    """The same words, each marked with whether it opens a line.

    What gets stored on a finished project, so the editor shows the lines
    the video was burned with and an edit to them survives the next burn.
    """
    out: list[Word] = []
    for line in plan_lines(words, max_per_line, language):
        for i, word in enumerate(line):
            out.append(word.model_copy(update={"starts_line": i == 0}))
    return out


def _chunk_words(
    words: list[Word], max_words_per_line: int, language: str = "en"
) -> list[SubtitleLine]:
    return [
        SubtitleLine(words=line, start_ms=line[0].start_ms, end_ms=line[-1].end_ms)
        for line in plan_lines(words, max_words_per_line, language)
    ]


# Uppercasing is not language-neutral, and the one case that matters here
# is Turkish. It has two i's — dotted and dotless — and `str.upper()` maps
# "i" to "I", which in Turkish is the *other* letter: "ritme" comes out
# "RITME" where it should read "RİTME". Wrong in a way a Turkish reader
# catches instantly and nobody else notices, and burned into the frame
# where it can't be corrected afterwards. The substitution runs before
# .upper() because "İ".upper() is already "İ"; the dotless "ı" needs no
# help, since "ı".upper() is correctly "I".
_UPPERCASE_PRE: dict[str, dict[int, str]] = {
    "tr": str.maketrans({"i": "İ"}),
    "az": str.maketrans({"i": "İ"}),
}


def _uppercase(text: str, language: str) -> str:
    table = _UPPERCASE_PRE.get(language.split("-")[0].lower())
    return (text.translate(table) if table else text).upper()


def _render_line_text(
    line: SubtitleLine, active_index: int, style: SubtitleStyle, language: str
) -> str:
    parts: list[str] = []
    for i, word in enumerate(line.words):
        text = _uppercase(word.text, language) if style.uppercase else word.text
        text = _sanitize(text)
        if i == active_index:
            # In a boxed style the glyphs stay readable and the *box*
            # changes colour — \3c is the box under BorderStyle 3, the
            # same tag that would be the outline otherwise. Recolouring
            # the text instead would put the highlight colour against a
            # filled background and lose most of its contrast.
            # And no scale-up in a box. The 12% that makes a word pop on
            # an outlined caption makes its box taller than the ones
            # beside it, so the strip comes out with a lump in the middle
            # — the colour is doing the work there anyway.
            if style.box:
                parts.append(f"{{\\3c{style.highlight_color}}}{text}{{\\r}}")
            else:
                parts.append(
                    f"{{\\c{style.highlight_color}\\fscx112\\fscy112}}{text}{{\\r}}"
                )
        else:
            parts.append(f"{{\\c{style.primary_color}}}{text}{{\\r}}")
    # Japanese and Chinese put no spaces between words. Joined with them,
    # a line read as separated syllables — and what Whisper or a
    # translation hands back for these is already cut into runs.
    unspaced = language.split("-")[0].lower() in ("ja", "zh")
    return ("" if unspaced else " ").join(parts)


def _events_for_line(line: SubtitleLine, style: SubtitleStyle, language: str) -> list[str]:
    events: list[str] = []
    for i, word in enumerate(line.words):
        start = _format_timestamp(word.start_ms)
        end = _format_timestamp(word.end_ms)
        text = _render_line_text(line, active_index=i, style=style, language=language)
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return events


def _header_for(style: SubtitleStyle, play_res: tuple[int, int], language: str = "en") -> str:
    return ASS_HEADER_TEMPLATE.format(
        play_res_x=play_res[0],
        play_res_y=play_res[1],
        # Resolved here rather than at the picker: the language is a
        # property of the project and the style is a preference, so
        # this is the last place that knows both.
        font_family=font_for(style.font_family, language),
        font_size=style.font_size,
        primary_color=style.primary_color,
        outline_color=style.outline_color,
        outline_width=style.outline_width,
        # BorderStyle 3 fills a box behind the text in OutlineColour
        # instead of stroking the glyphs with it. One number, and it is
        # the whole difference between a caption that floats over the
        # picture and one that sits in a block — which is the look most
        # short-form video actually uses, and the only one this could not
        # previously produce with a single font.
        border_style=3 if style.box else 1,
        shadow=style.shadow,
        spacing=style.letter_spacing,
        alignment=_ALIGNMENT_BY_POSITION.get(style.position, 2),
        margin_v=_MARGIN_V_BY_POSITION.get(style.position, 260),
    )


# ASS alignment codes for a user-placed overlay. Same numpad geometry as
# the caption alignments above, but always centred horizontally.
_OVERLAY_ALIGNMENT = {"top": 8, "middle": 5, "bottom": 2}


def _sanitize(text: str) -> str:
    """Strip the two characters that delimit ASS override tags.

    Everything drawn here is eventually user-supplied — a transcript the
    user corrected, or an overlay they typed. A stray brace doesn't just
    render wrong, it opens an override block and the rest of the line is
    swallowed as formatting codes.
    """
    return text.replace("{", "").replace("}", "").replace("\n", " ")


def _events_for_overlays(overlays: list[TextOverlay]) -> list[str]:
    """Authored text, as events in the same file as the captions.

    Drawn by libass rather than by a separate ffmpeg `drawtext` filter:
    one burn-in pass instead of two, and the overlay inherits the same
    font rendering and outline as the captions, so the two don't look like
    they came from different tools.
    """
    events: list[str] = []
    for overlay in overlays:
        if overlay.end_ms <= overlay.start_ms or not overlay.text.strip():
            continue
        align = _OVERLAY_ALIGNMENT.get(str(overlay.position), 8)
        tags = f"{{\\an{align}\\fs{overlay.font_size}\\c{overlay.color}}}"
        events.append(
            f"Dialogue: 1,{_format_timestamp(overlay.start_ms)},"
            f"{_format_timestamp(overlay.end_ms)},Default,,0,0,0,,"
            f"{tags}{_sanitize(overlay.text)}"
        )
    return events


def build_ass_from_words(
    words: list[Word],
    style: SubtitleStyle,
    output_path: Path,
    play_res: tuple[int, int] = (1080, 1920),
    overlays: list[TextOverlay] | None = None,
    language: str = "en",
    censor: bool = False,
    censor_extra: str = "",
) -> Path:
    """Build an .ass file from words already timed against the finished
    video.

    This is the general form. A generated project's words start out timed
    per scene and have to be offset first (see `build_ass_subtitles`); an
    uploaded video's words come straight out of Whisper already absolute,
    with no scenes to offset by. Both end up here.

    `censor` masks the strong language on screen. It is applied here, to
    a copy, rather than to the stored transcript — the words keep their
    real text so the editor shows what was said and turning the toggle
    off renders back to it. The matching bleep is `render_engine`'s;
    masking here alone would leave it audible.
    """
    if censor:
        words = profanity.censor_words(words, language, censor_extra)

    events: list[str] = []
    for line in _chunk_words(words, style.max_words_per_line, language):
        events.extend(_events_for_line(line, style, language))
    # Layer 1, so authored text draws above the caption track where they
    # happen to occupy the same moment.
    events.extend(_events_for_overlays(overlays or []))

    output_path.write_text(
        _header_for(style, play_res, language) + "\n".join(events) + "\n", encoding="utf-8"
    )
    return output_path


def shift_words_from(words: list[Word], at_ms: int, delta_ms: int) -> list[Word]:
    """Move every word at or after `at_ms` by `delta_ms`.

    For when one scene of a finished video is re-encoded and comes back a
    hair longer or shorter than it was. The obvious alternative — rebuild
    the track with absolute_words() — is wrong here and quietly so: once a
    project has been through /edit, `edit.captions` is the authority and
    holds text the user typed. Rebuilding from the scenes throws that away
    and replaces it with the transcript, which no test of timings would
    catch.

    A no-op delta returns the same words rather than copies, so the common
    case — a re-roll that changes nothing about the timeline — costs
    nothing and cannot introduce drift.
    """
    if delta_ms == 0:
        return words
    return [
        Word(
            text=w.text,
            start_ms=w.start_ms + delta_ms if w.start_ms >= at_ms else w.start_ms,
            end_ms=w.end_ms + delta_ms if w.start_ms >= at_ms else w.end_ms,
            confidence=w.confidence,
            starts_line=w.starts_line,
        )
        for w in words
    ]


def scene_start_ms(scenes: list[Scene], index: int) -> int:
    """Where a scene begins on the concatenated timeline.

    The same accumulation absolute_words does, stopped early — kept beside
    it so the two cannot drift apart about what a scene's offset means.
    """
    offset_ms = 0
    for scene in scenes[:index]:
        offset_ms += scene.audio.duration_ms or int(scene.duration_s * 1000)
    return offset_ms


def absolute_words(scenes: list[Scene]) -> list[Word]:
    """Flatten per-scene word timings onto the concatenated timeline.

    Each scene's `audio.words` are relative to that scene's own audio clip,
    so every scene's duration has to accumulate into the offset — the same
    arithmetic the frontend's TranscriptPanel does to map a click back to a
    playback position.
    """
    out: list[Word] = []
    offset_ms = 0
    for scene in scenes:
        out.extend(
            Word(
                text=w.text,
                start_ms=w.start_ms + offset_ms,
                end_ms=w.end_ms + offset_ms,
                confidence=w.confidence,
            )
            for w in scene.audio.words
        )
        offset_ms += scene.audio.duration_ms or int(scene.duration_s * 1000)
    return out


def build_ass_subtitles(
    scenes: list[Scene],
    style: SubtitleStyle,
    output_path: Path,
    play_res: tuple[int, int] = (1080, 1920),
    language: str = "en",
    censor: bool = False,
    censor_extra: str = "",
) -> Path:
    """Build a single .ass file covering the full timeline of a generated
    project."""
    return build_ass_from_words(
        absolute_words(scenes),
        style,
        output_path,
        play_res,
        language=language,
        censor=censor,
        censor_extra=censor_extra,
    )
