"""Bleeping the strong language, and masking it on screen.

Both halves or neither: audio silenced with the word still written across
the frame censors nothing, and `***` over an audible swear is worse than
leaving it alone. These check that the two agree, and that the matching
does not fire on words nobody swore.

The false positives matter more than the misses here. A missed word
leaves the user where they already were; a wrongly-bleeped one puts a
tone over an innocent sentence and the user cannot see why.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.project import SubtitleStyle, Word
from app.services import profanity


def _words(*pairs: tuple[str, int]) -> list[Word]:
    """Words at 500ms each, starting where the last one ended."""
    out: list[Word] = []
    at = 0
    for text, gap in pairs:
        out.append(Word(text=text, start_ms=at, end_ms=at + 500, confidence=None))
        at += 500 + gap
    return out


# --- what gets matched --------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language"),
    [("shit", "en"), ("Shit,", "en"), ("FUCKING", "en"), ("siktir", "tr"),
     ("Scheiße", "de"), ("merde", "fr"), ("сука", "ru")],
)
def test_the_listed_words_are_caught_however_they_are_written(text, language):
    """Whisper attaches punctuation and follows the speaker's casing, so
    neither can be assumed away."""
    assert profanity.is_profane(text, language)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        # The classic substring failure. "Scunthorpe" is the name of the
        # problem for a reason.
        ("Scunthorpe", "en"),
        ("assassin", "en"),
        ("classic", "en"),
        ("shitake", "en"),
        # Turkish, where a careless casefold is the trap: casefold maps
        # I to i, so "SIKINTI" would become "sikinti" and a prefix match
        # would fire on an ordinary word meaning "trouble".
        ("sıkıntı", "tr"),
        ("SIKINTI", "tr"),
        ("pikap", "tr"),
    ],
)
def test_innocent_words_are_left_alone(text, language):
    assert not profanity.is_profane(text, language)


def test_a_language_with_no_list_falls_back_rather_than_doing_nothing():
    """A toggle that silently does nothing is worse than one that catches
    only the English — which is what a video in an unlisted language is
    most likely to contain anyway."""
    assert profanity.is_profane("fuck", "ja")


def test_a_deployment_can_add_its_own():
    assert not profanity.is_profane("bother", "en")
    assert profanity.is_profane("bother", "en", extra="bother, drat")


# --- the two halves agree -----------------------------------------------


def test_the_caption_is_masked_where_the_audio_is_bleeped():
    """The same words drive both, so a word that is silenced is a word
    that shows as ***. Checking them together is the point."""
    words = _words(("this", 0), ("shit", 0), ("works", 0))

    masked = profanity.censor_words(words, "en")
    spans = profanity.spans(words, "en")

    assert [w.text for w in masked] == ["this", profanity.MASK, "works"]
    assert len(spans) == 1
    # The one bleep covers the one masked word, padded.
    start, end = spans[0]
    assert start <= 0.5 and end >= 1.0


def test_the_stored_transcript_is_never_rewritten():
    """The editor shows what was actually said, and turning the toggle
    off has to render back to it — so masking works on a copy."""
    words = _words(("shit", 0))

    profanity.censor_words(words, "en")

    assert words[0].text == "shit"


def test_nothing_to_censor_produces_no_bleeps():
    """An ordinary video must not get an ffmpeg audio filter it does not
    need — the chain is skipped entirely when this is empty."""
    assert profanity.spans(_words(("a", 0), ("clean", 0), ("video", 0)), "en") == []


# --- the spans themselves -----------------------------------------------


def test_adjacent_swearing_becomes_one_bleep():
    """A tone that stops and restarts in a 40ms gap sounds like a fault
    rather than a censor."""
    spans = profanity.spans(_words(("shit", 0), ("fuck", 0)), "en")

    assert len(spans) == 1


def test_swearing_apart_stays_apart():
    spans = profanity.spans(_words(("shit", 4000), ("fuck", 0)), "en")

    assert len(spans) == 2


def test_the_bleep_is_padded_past_the_word():
    """Whisper's boundaries land on the vowel, so a cut exactly to the
    timestamps leaves the opening consonant — usually the recognisable
    part — audible."""
    # Not the first word: a span at zero is clamped, which is a different
    # property and has its own test below.
    word = _words(("say", 0), ("shit", 0))[1]
    (start, end), = profanity.spans([word], "en")

    assert start < word.start_ms / 1000
    assert end > word.end_ms / 1000


def test_a_bleep_at_the_very_start_does_not_go_negative():
    """ffmpeg's `between(t,...)` with a negative start is not an error and
    not what was meant."""
    words = [Word(text="shit", start_ms=0, end_ms=400, confidence=None)]

    (start, _), = profanity.spans(words, "en")

    assert start == 0.0


# --- and it reaches the subtitle file ------------------------------------


def test_the_mask_is_what_lands_in_the_ass_file(tmp_path):
    from app.engines import subtitle_engine

    words = _words(("say", 0), ("shit", 0))
    path = subtitle_engine.build_ass_from_words(
        words, SubtitleStyle(), tmp_path / "c.ass", language="en", censor=True
    )
    body = path.read_text(encoding="utf-8")

    assert "***" in body
    assert "SHIT" not in body.upper().replace("***", "")


def test_without_the_toggle_the_word_is_left_alone(tmp_path):
    from app.engines import subtitle_engine

    words = _words(("say", 0), ("shit", 0))
    path = subtitle_engine.build_ass_from_words(
        words, SubtitleStyle(), tmp_path / "c.ass", language="en"
    )

    assert "***" not in path.read_text(encoding="utf-8")


# --- the filtergraph the bleep produces ---------------------------------
#
# These read the ffmpeg arguments rather than running ffmpeg. The bug they
# exist for rendered perfectly: a graph that consumed the censored voice
# twice produced a valid file with the swearing still in it, and nothing
# short of measuring the output's spectrum said so.


async def _graph(**kwargs) -> str:
    from unittest.mock import patch

    from app.engines import render_engine
    from app.schemas.project import MusicConfig

    captured: dict = {}

    async def fake_run(args, binary):
        captured["args"] = args

    with patch.object(render_engine, "_run_ffmpeg", fake_run):
        await render_engine.finalize_render(
            Path("in.mp4"),
            Path("c.ass"),
            kwargs.pop("music", MusicConfig(enabled=False)),
            Path("out.mp4"),
            target=render_engine.RenderTarget(540, 960, 25),
            **kwargs,
        )
    args = captured["args"]
    return args[args.index("-filter_complex") + 1]


async def test_a_censored_voice_is_never_consumed_twice():
    """A filtergraph label can feed exactly one filter — an input stream
    can feed several, which is why this worked before the bleep chain
    existed. The ducked mix reads the voice twice: once to key the
    compressor and once as the signal. Without an explicit split, one of
    them silently got nothing and the swearing came back."""
    from app.schemas.project import MusicConfig

    graph = await _graph(
        music=MusicConfig(enabled=True, track_path="t.mp3", duck_on_voice=True),
        bleeps=[(1.0, 2.0)],
    )

    assert graph.count("[speech]") == 2  # produced once, split once
    assert "asplit=2[voice_key][voice_mix]" in graph
    assert graph.count("[voice_key]") == 2
    assert graph.count("[voice_mix]") == 2


async def test_without_music_the_censored_voice_is_what_gets_mapped():
    graph = await _graph(bleeps=[(1.0, 2.0)])

    assert "[speech]" in graph
    assert "asplit" not in graph


async def test_no_swearing_means_no_audio_filter_at_all():
    """An ordinary render must not pay for a filter chain it does not
    need, and must not have its audio re-encoded through one."""
    graph = await _graph(bleeps=None)

    assert "sine=" not in graph
    assert "speech" not in graph


async def test_the_spans_reach_ffmpeg_as_an_enable_expression():
    graph = await _graph(bleeps=[(1.0, 2.0), (5.5, 6.25)])

    assert "between(t,1.000,2.000)+between(t,5.500,6.250)" in graph
    # And the tone is gated by the negation of the same expression, or it
    # would play over the whole video.
    assert "not(between(t,1.000,2.000)+between(t,5.500,6.250))" in graph
