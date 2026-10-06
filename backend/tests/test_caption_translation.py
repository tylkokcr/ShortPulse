"""Captions translated over the original speech."""

from app.engines.subtitle_engine import SubtitleLine, _render_line_text
from app.schemas.project import Segment, SubtitleStyle, Word
from app.services.dubbing import translated_caption_words


def _segment(text: str, start_ms: int, end_ms: int) -> Segment:
    return Segment(
        text=text,
        start_ms=start_ms,
        end_ms=end_ms,
        words=[Word(text=text, start_ms=start_ms, end_ms=end_ms)],
    )


def test_each_translation_fills_the_time_its_sentence_was_spoken() -> None:
    segments = [_segment("Merhaba dünya", 0, 2000), _segment("Nasılsın", 2000, 3000)]
    words = translated_caption_words(segments, ["Hello world", "How are you"], "en")

    assert [w.text for w in words] == ["Hello", "world", "How", "are", "you"]
    assert words[0].start_ms == 0 and words[1].end_ms == 2000
    assert words[2].start_ms == 2000 and words[-1].end_ms == 3000


def test_longer_words_are_given_longer_on_screen() -> None:
    words = translated_caption_words([_segment("x", 0, 1000)], ["a extraordinarily"], "en")
    short, long = words
    assert (long.end_ms - long.start_ms) > (short.end_ms - short.start_ms)


def test_japanese_is_cut_into_short_runs_not_one_sentence() -> None:
    words = translated_caption_words(
        [_segment("x", 0, 3000)], ["このモデルはイタリアの生地でできています。"], "ja"
    )
    assert len(words) > 4
    assert all(len(w.text) <= 3 for w in words)
    assert "".join(w.text for w in words) == "このモデルはイタリアの生地でできています。"


def test_a_missing_translation_drops_nothing_after_it() -> None:
    segments = [_segment("bir", 0, 1000), _segment("iki", 1000, 2000)]
    words = translated_caption_words(segments, ["", "two"], "en")
    assert [w.text for w in words] == ["two"]
    assert words[0].start_ms == 1000


def test_japanese_lines_are_joined_without_spaces() -> None:
    runs = [
        Word(text=t, start_ms=i * 100, end_ms=i * 100 + 100)
        for i, t in enumerate(["この", "モデ", "ル"])
    ]
    line = SubtitleLine(words=runs, start_ms=0, end_ms=300)
    style = SubtitleStyle(uppercase=False)

    ja = _render_line_text(line, 0, style, "ja")
    en = _render_line_text(line, 0, style, "en")

    assert "} {" not in ja
    assert "} {" in en
