
import pytest

from app.schemas.project import ProjectConfig, ProjectSource, Segment, VoiceConfig
from app.services import credits, dubbing


def _segment(text: str, start_ms: int, end_ms: int) -> Segment:
    return Segment(text=text, start_ms=start_ms, end_ms=end_ms)


# --------------------------------------------------------------------------
# Fitting a sentence into the slot its original occupied
# --------------------------------------------------------------------------


async def test_a_line_that_overruns_its_slot_is_respoken_faster(tmp_path, monkeypatch):
    """The whole reason `length_scale` got plumbed through: a translation
    that runs long would otherwise talk over the sentence after it."""
    calls: list[float | None] = []
    durations = iter([2300, 2050])

    async def fake_synthesize(text, voice, output_path, language, length_scale=None):
        calls.append(length_scale)
        return output_path

    async def fake_probe(path, ffprobe_binary="ffprobe"):
        return next(durations)

    monkeypatch.setattr(dubbing.audio_engine, "synthesize_line", fake_synthesize)
    monkeypatch.setattr(dubbing.render_engine, "probe_duration_ms", fake_probe)

    spoken = await dubbing._speak_into_slot(
        "uzun bir cümle", 2000, VoiceConfig(), "tr", tmp_path / "a.wav", "ffprobe"
    )

    assert calls == [None, pytest.approx(2000 / 2300, abs=0.01)]
    assert spoken == 2050


async def test_a_line_already_close_enough_is_not_respoken(tmp_path, monkeypatch):
    """A second synthesis is the slowest thing in the dub. Under the
    tolerance nobody can hear the difference, so it isn't paid for."""
    calls: list[float | None] = []

    async def fake_synthesize(text, voice, output_path, language, length_scale=None):
        calls.append(length_scale)
        return output_path

    async def fake_probe(path, ffprobe_binary="ffprobe"):
        return 2050

    monkeypatch.setattr(dubbing.audio_engine, "synthesize_line", fake_synthesize)
    monkeypatch.setattr(dubbing.render_engine, "probe_duration_ms", fake_probe)

    await dubbing._speak_into_slot(
        "kısa", 2000, VoiceConfig(), "tr", tmp_path / "a.wav", "ffprobe"
    )

    assert calls == [None]


async def test_speed_correction_is_clamped(tmp_path, monkeypatch):
    """A sentence that cannot fit is left long rather than sped up until
    it stops sounding like a person."""
    calls: list[float | None] = []

    async def fake_synthesize(text, voice, output_path, language, length_scale=None):
        calls.append(length_scale)
        return output_path

    async def fake_probe(path, ffprobe_binary="ffprobe"):
        return 10_000

    monkeypatch.setattr(dubbing.audio_engine, "synthesize_line", fake_synthesize)
    monkeypatch.setattr(dubbing.render_engine, "probe_duration_ms", fake_probe)

    await dubbing._speak_into_slot(
        "çok uzun", 1000, VoiceConfig(), "tr", tmp_path / "a.wav", "ffprobe"
    )

    assert calls[1] == dubbing._MIN_LENGTH_SCALE


# --------------------------------------------------------------------------
# Laying the clips out against the original timing
# --------------------------------------------------------------------------


def test_each_clip_is_placed_at_an_absolute_time(tmp_path):
    """`adelay` per clip, not a concatenation: a sentence that came out
    long must move nothing except itself, or every later line drifts out
    of sync with a picture that never moved."""
    args = dubbing._mix_args(
        [(tmp_path / "a.wav", 0), (tmp_path / "b.wav", 2500), (tmp_path / "c.wav", 7100)],
        12_000,
        tmp_path / "out.wav",
    )
    graph = args[args.index("-filter_complex") + 1]

    assert "adelay=delays=0:all=1" in graph
    assert "adelay=delays=2500:all=1" in graph
    assert "adelay=delays=7100:all=1" in graph
    # amix would otherwise divide every input by their count, quietening
    # the dub in proportion to how many sentences it has.
    assert "normalize=0" in graph
    assert "apad=whole_dur=12.000" in graph
    assert args[args.index("-t") + 1] == "12.000"


def test_a_video_with_no_usable_speech_still_gets_a_full_length_track(tmp_path):
    """Handing back nothing would let the mux fall through to the source
    audio, and the 'dub' would silently be the original."""
    args = dubbing._mix_args([], 5000, tmp_path / "out.wav")

    assert "anullsrc" in " ".join(args)
    assert args[args.index("-t") + 1] == "5.000"


# --------------------------------------------------------------------------
# Translation
# --------------------------------------------------------------------------


async def test_translations_are_matched_by_index_not_by_order(monkeypatch):
    """A model that returns the lines out of order must not shift every
    sentence onto the wrong slot."""

    async def fake_complete_json(llm, system_prompt, prompt):
        return {"lines": [{"i": 2, "text": "third"}, {"i": 0, "text": "first"},
                          {"i": 1, "text": "second"}]}

    monkeypatch.setattr(dubbing.script_engine, "complete_json", fake_complete_json)

    segments = [_segment("bir", 0, 1000), _segment("iki", 1000, 2000), _segment("üç", 2000, 3000)]
    out = await dubbing.translate_segments(segments, "tr", "en", None)

    assert out == ["first", "second", "third"]


async def test_a_dropped_line_keeps_its_original_text(monkeypatch):
    """A gap would silently delete a sentence from the video. Leaving the
    source text in makes the failure audible instead."""

    async def fake_complete_json(llm, system_prompt, prompt):
        return {"lines": [{"i": 0, "text": "first"}]}

    monkeypatch.setattr(dubbing.script_engine, "complete_json", fake_complete_json)

    segments = [_segment("bir", 0, 1000), _segment("iki", 1000, 2000)]
    out = await dubbing.translate_segments(segments, "tr", "en", None)

    assert out == ["first", "iki"]


async def test_a_response_without_lines_is_an_error(monkeypatch):
    async def fake_complete_json(llm, system_prompt, prompt):
        return {"nope": []}

    monkeypatch.setattr(dubbing.script_engine, "complete_json", fake_complete_json)

    with pytest.raises(dubbing.DubbingError):
        await dubbing.translate_segments([_segment("bir", 0, 1000)], "tr", "en", None)


# --------------------------------------------------------------------------
# Captions describing the new audio
# --------------------------------------------------------------------------


def test_caption_words_span_the_sentence_they_belong_to():
    """The dub has no transcript of its own. Words are spread across the
    sentence's own span so the line on screen is the line being spoken."""
    words = dubbing.words_from_segments([_segment("one two three four", 1000, 3000)])

    assert [w.text for w in words] == ["one", "two", "three", "four"]
    assert words[0].start_ms == 1000
    assert words[-1].end_ms <= 3100
    assert all(a.start_ms <= b.start_ms for a, b in zip(words, words[1:], strict=False))


# --------------------------------------------------------------------------
# Price
# --------------------------------------------------------------------------


def test_a_dub_costs_more_than_a_caption_pass():
    captioned = ProjectConfig(topic="x", source=ProjectSource.UPLOAD)
    dubbed = ProjectConfig(topic="x", source=ProjectSource.UPLOAD, dub_language="tr")

    assert credits.cost_for(captioned) == credits.AUTOCAPTION_COST
    assert credits.cost_for(dubbed) == credits.DUB_COST
    assert credits.DUB_COST > credits.AUTOCAPTION_COST


def test_dub_language_must_be_a_language_code():
    with pytest.raises(ValueError):
        ProjectConfig(topic="x", source=ProjectSource.UPLOAD, dub_language="turkish")
