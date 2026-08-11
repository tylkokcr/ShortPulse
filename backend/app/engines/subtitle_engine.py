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

from dataclasses import dataclass
from pathlib import Path

from app.schemas.project import Scene, SubtitleStyle, Word

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
Style: Default,{font_family},{font_size},{primary_color},&H000000FF,{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{outline_width},0,{alignment},60,60,{margin_v},1

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


def _chunk_words(words: list[Word], max_words_per_line: int) -> list[SubtitleLine]:
    lines: list[SubtitleLine] = []
    for i in range(0, len(words), max_words_per_line):
        chunk = words[i : i + max_words_per_line]
        if not chunk:
            continue
        lines.append(SubtitleLine(words=chunk, start_ms=chunk[0].start_ms, end_ms=chunk[-1].end_ms))
    return lines


def _render_line_text(line: SubtitleLine, active_index: int, style: SubtitleStyle) -> str:
    parts: list[str] = []
    for i, word in enumerate(line.words):
        text = word.text.upper() if style.uppercase else word.text
        text = text.replace("{", "").replace("}", "")  # strip user text that could break override tags
        if i == active_index:
            parts.append(f"{{\\c{style.highlight_color}\\fscx112\\fscy112}}{text}{{\\r}}")
        else:
            parts.append(f"{{\\c{style.primary_color}}}{text}{{\\r}}")
    return " ".join(parts)


def _events_for_line(line: SubtitleLine, style: SubtitleStyle) -> list[str]:
    events: list[str] = []
    for i, word in enumerate(line.words):
        start = _format_timestamp(word.start_ms)
        end = _format_timestamp(word.end_ms)
        text = _render_line_text(line, active_index=i, style=style)
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return events


def _header_for(style: SubtitleStyle, play_res: tuple[int, int]) -> str:
    return ASS_HEADER_TEMPLATE.format(
        play_res_x=play_res[0],
        play_res_y=play_res[1],
        font_family=style.font_family,
        font_size=style.font_size,
        primary_color=style.primary_color,
        outline_color=style.outline_color,
        outline_width=style.outline_width,
        alignment=_ALIGNMENT_BY_POSITION.get(style.position, 2),
        margin_v=_MARGIN_V_BY_POSITION.get(style.position, 260),
    )


def build_ass_from_words(
    words: list[Word],
    style: SubtitleStyle,
    output_path: Path,
    play_res: tuple[int, int] = (1080, 1920),
) -> Path:
    """Build an .ass file from words already timed against the finished
    video.

    This is the general form. A generated project's words start out timed
    per scene and have to be offset first (see `build_ass_subtitles`); an
    uploaded video's words come straight out of Whisper already absolute,
    with no scenes to offset by. Both end up here.
    """
    events: list[str] = []
    for line in _chunk_words(words, style.max_words_per_line):
        events.extend(_events_for_line(line, style))

    output_path.write_text(
        _header_for(style, play_res) + "\n".join(events) + "\n", encoding="utf-8"
    )
    return output_path


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
) -> Path:
    """Build a single .ass file covering the full timeline of a generated
    project."""
    return build_ass_from_words(absolute_words(scenes), style, output_path, play_res)
