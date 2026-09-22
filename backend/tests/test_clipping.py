import pytest

from app.schemas.project import LLMConfig, Segment
from app.services import clipping


def _transcript(count: int = 60, seconds_each: float = 5.0) -> list[Segment]:
    """A transcript long enough to take clips out of: `count` sentences,
    back to back, five seconds apiece."""
    return [
        Segment(
            text=f"sentence {i}",
            start_ms=round(i * seconds_each * 1000),
            end_ms=round((i + 1) * seconds_each * 1000),
        )
        for i in range(count)
    ]


def _answer(monkeypatch, moments):
    """Stub the model. Nothing here should reach a network."""

    async def fake_complete_json(config, system_prompt, prompt):
        return {"moments": moments}

    monkeypatch.setattr(clipping.script_engine, "complete_json", fake_complete_json)


CONFIG = LLMConfig()


# --------------------------------------------------------------------------
# Indices rather than timestamps — the reason the module works this way
# --------------------------------------------------------------------------


async def test_seconds_come_from_the_transcript_not_the_model(monkeypatch):
    """The model names segments; the clock comes from Whisper. A model
    that also volunteered timestamps must not be believed over them."""
    _answer(monkeypatch, [{"first": 4, "last": 8, "title": "A point", "start_s": 999}])

    [moment] = await clipping.pick_moments(_transcript(), CONFIG)

    assert moment.start_s == 20.0
    assert moment.end_s == 45.0


async def test_an_index_outside_the_transcript_is_dropped(monkeypatch):
    """The failure mode picking indices converts hallucination into: a
    number that is not in the list."""
    _answer(monkeypatch, [{"first": 0, "last": 5000, "title": "Invented"}])

    assert await clipping.pick_moments(_transcript(), CONFIG) == []


async def test_a_backwards_range_is_dropped(monkeypatch):
    _answer(monkeypatch, [{"first": 20, "last": 3, "title": "Backwards"}])

    assert await clipping.pick_moments(_transcript(), CONFIG) == []


# --------------------------------------------------------------------------
# Length
# --------------------------------------------------------------------------


async def test_a_moment_over_the_ceiling_is_trimmed_to_a_sentence_boundary(monkeypatch):
    """Overshoot is the model doing the task and misjudging length, so it
    is pulled back — but only to a segment edge, never mid-sentence."""
    _answer(monkeypatch, [{"first": 0, "last": 40, "title": "Far too long"}])

    [moment] = await clipping.pick_moments(_transcript(), CONFIG)

    assert moment.duration_s <= clipping.MAX_CLIP_S
    # Every segment ends on a multiple of five, so landing on one proves
    # the trim stopped at a boundary.
    assert moment.end_s % 5 == 0


async def test_a_moment_under_the_floor_is_dropped(monkeypatch):
    """Two segments is ten seconds, and there is no point to be made in
    ten seconds."""
    _answer(monkeypatch, [{"first": 0, "last": 1, "title": "Too short"}])

    assert await clipping.pick_moments(_transcript(), CONFIG) == []


async def test_a_single_segment_longer_than_the_ceiling_is_dropped(monkeypatch):
    """Trimming has nowhere to go, and cutting inside the segment would
    land mid-sentence."""
    long_segment = [Segment(text="one long ramble", start_ms=0, end_ms=200_000)]
    _answer(monkeypatch, [{"first": 0, "last": 0, "title": "Unsplittable"}])

    assert await clipping.pick_moments(long_segment, CONFIG) == []


# --------------------------------------------------------------------------
# Overlap, ordering, quota
# --------------------------------------------------------------------------


async def test_overlapping_moments_lose_the_later_one(monkeypatch):
    _answer(
        monkeypatch,
        [
            {"first": 0, "last": 5, "title": "First"},
            {"first": 3, "last": 9, "title": "Overlaps the first"},
        ],
    )

    moments = await clipping.pick_moments(_transcript(), CONFIG)

    assert [m.title for m in moments] == ["First"]


async def test_moments_come_back_in_playing_order(monkeypatch):
    """The model may answer in any order; the cuts happen along a
    timeline."""
    _answer(
        monkeypatch,
        [
            {"first": 30, "last": 34, "title": "Later"},
            {"first": 0, "last": 4, "title": "Earlier"},
        ],
    )

    moments = await clipping.pick_moments(_transcript(), CONFIG)

    assert [m.title for m in moments] == ["Earlier", "Later"]
    assert moments[0].start_s < moments[1].start_s


async def test_more_moments_than_asked_for_are_cut_off(monkeypatch):
    _answer(
        monkeypatch,
        [{"first": i * 6, "last": i * 6 + 4, "title": f"Moment {i}"} for i in range(6)],
    )

    assert len(await clipping.pick_moments(_transcript(), CONFIG, wanted=2)) == 2


async def test_fewer_good_moments_than_asked_for_is_a_real_answer(monkeypatch):
    """One usable moment yields one clip. Padding to the quota would
    charge for cuts nobody wants."""
    _answer(
        monkeypatch,
        [
            {"first": 0, "last": 4, "title": "Good"},
            {"first": 10, "last": 11, "title": "Too short"},
            {"first": 900, "last": 950, "title": "Invented"},
        ],
    )

    assert len(await clipping.pick_moments(_transcript(), CONFIG, wanted=3)) == 1


# --------------------------------------------------------------------------
# Refusing to run
# --------------------------------------------------------------------------


async def test_a_short_video_is_refused_rather_than_diced(monkeypatch):
    """Three moments out of two minutes is most of the video, which is
    not an extraction — the caption path already handles it whole."""
    _answer(monkeypatch, [{"first": 0, "last": 4, "title": "Anything"}])

    with pytest.raises(clipping.NotEnoughSource):
        await clipping.pick_moments(_transcript(count=12), CONFIG)


async def test_no_transcript_is_no_moments(monkeypatch):
    """Whisper drops silent segments, so a video with no speech in it
    arrives here empty rather than as an error."""
    assert await clipping.pick_moments([], CONFIG) == []


async def test_a_model_that_answers_with_nonsense_yields_nothing(monkeypatch):
    """Never raises at the caller. A bad answer is zero clips, which the
    upload path reports as 'nothing worth cutting'."""

    async def fake_complete_json(config, system_prompt, prompt):
        return {"moments": "not a list"}

    monkeypatch.setattr(clipping.script_engine, "complete_json", fake_complete_json)

    assert await clipping.pick_moments(_transcript(), CONFIG) == []


# --------------------------------------------------------------------------
# What it costs
# --------------------------------------------------------------------------


def _upload_config(**kwargs):
    from app.schemas.project import ProjectConfig, ProjectSource

    return ProjectConfig(topic="x", source=ProjectSource.UPLOAD, **kwargs)


def test_an_extraction_is_priced_per_clip():
    """Each clip is a cut, a transcription and a burn — an autocaption job
    — so it is priced as one. The shared pass over the source is not
    billed, which is what makes three clips cost the same as three
    captions."""
    from app.services import credits

    assert credits.cost_for(_upload_config(clip_count=3)) == 3 * credits.AUTOCAPTION_COST


def test_clips_are_priced_ahead_of_the_dub_rate():
    """clip_count and dub_language cannot both be set — the route refuses
    it — but the pricing must not depend on that being enforced
    elsewhere."""
    from app.services import credits

    config = _upload_config(clip_count=2, dub_language="tr")
    assert credits.cost_for(config) == 2 * credits.AUTOCAPTION_COST


def test_a_plain_upload_is_unchanged():
    from app.services import credits

    assert credits.cost_for(_upload_config()) == credits.AUTOCAPTION_COST
    assert credits.cost_for(_upload_config(dub_language="tr")) == credits.DUB_COST
