"""Keeping the image model away from the shots it cannot draw.

Written after comparing a paid `fast_hybrid` render against a `stock_media`
one on the same topic. The generated frames were the better product by a
wide margin — faces convincing, the same subject across every scene — with
one exception that ruined the video on its own: a bath scene came back as a
melted foot over a tub edge.

The negative prompt already banned deformed hands and fingers and did not
help, because the problem was not the model rendering a foot badly. It was
being asked for a foot at all. So the fix is upstream, in what the script
engine tells the LLM to ask for, and the negatives are only the backstop.

These pin both halves. They assert on wording rather than behaviour because
the prompt *is* the behaviour here — there is nothing else between the
topic and the picture.
"""

from __future__ import annotations

import pytest

from app.engines.script_engine import _build_system_prompt
from app.engines.visual_engine import DEFAULT_NEGATIVE_PROMPT
from app.schemas.project import VideoLength
from app.services.art_styles import ART_STYLES


def _generated_prompt() -> str:
    return _build_system_prompt(VideoLength.SHORT, "en", visual_mode="fast_hybrid")


# --- what the LLM is told to ask for ------------------------------------


def test_generated_prompts_are_steered_to_close_and_medium_shots():
    prompt = _generated_prompt()
    assert "close-up" in prompt
    assert "medium shot" in prompt


def test_generated_prompts_are_steered_away_from_extremities():
    """The three framings that produced the unusable frame, named
    explicitly. A general 'keep it simple' would not have caught a bath
    scene, because nothing about it reads as complicated."""
    prompt = _generated_prompt()
    for banned in ("full-body", "hands or feet", "lying down"):
        assert banned in prompt, f"framing rule no longer rules out {banned!r}"


def test_the_frame_holds_at_most_one_person():
    """The first version of this rule only ruled out people *touching*,
    and the next paid render put six photographers in a frame — nobody
    touching, twelve feet to get wrong, and they failed in the foreground.
    A count is what closes that; 'don't interact' does not."""
    prompt = _generated_prompt()
    assert "At most one person in frame" in prompt


def test_crowds_are_named_rather_than_implied():
    """Every word the failing scene could have been written as. The model
    obliges whichever one the scriptwriter reaches for, so ruling out
    'crowd' alone would leave 'group' and 'audience' open."""
    prompt = _generated_prompt()
    for banned in ("crowd", "group", "team", "audience"):
        assert banned in prompt, f"framing rule no longer rules out {banned!r}"


def test_stock_prompts_are_not_given_framing_rules():
    """A stock search cannot be framed — the rule would be instructions to
    a library that only matches keywords, and the stock rule is terse on
    purpose because every token of it is generated and then thrown away."""
    prompt = _build_system_prompt(VideoLength.SHORT, "en", visual_mode="stock_media")
    assert "close-up" not in prompt
    assert "search keywords" in prompt


def test_the_text_rule_survived_the_rewrite():
    """The older, separate failure: legible writing is still beyond the
    model, and that rule shares the block the framing rule was added to."""
    assert "legible text" in _generated_prompt()


# --- the backstop, for when it asks anyway ------------------------------


@pytest.mark.parametrize("style", ART_STYLES, ids=lambda s: s.id)
def test_every_style_rules_out_deformed_feet(style):
    """Fingers were covered and toes were not, which is exactly the gap the
    bath frame fell through. Parametrised so a style added later cannot
    quietly ship without it."""
    assert "deformed feet" in style.negative_prompt
    assert "extra toes" in style.negative_prompt


@pytest.mark.parametrize("style", ART_STYLES, ids=lambda s: s.id)
def test_every_style_rules_out_a_crowd(style):
    assert "crowd" in style.negative_prompt
    assert "group of people" in style.negative_prompt


@pytest.mark.parametrize("style", ART_STYLES, ids=lambda s: s.id)
def test_no_style_bans_people_outright(style):
    """The negatives name the crowd, not people.

    Out-of-focus figures behind a portrait came back reading as depth
    rather than as errors, and every good frame in the reference render
    had them. A bare "people" or "person" here would cost that and fix
    nothing, because what fails is a crowd being the subject — which the
    framing rule in script_engine is the precise instrument for.
    """
    terms = {t.strip() for t in style.negative_prompt.split(",")}
    assert "people" not in terms
    assert "person" not in terms
    assert "background people" not in terms


def test_the_default_negative_prompt_matches_the_styles():
    """visual_engine's default applies when a scene supplies no negative of
    its own, so a gap here is a gap on the same renders."""
    for term in ("deformed feet", "extra toes", "crowd", "group of people"):
        assert term in DEFAULT_NEGATIVE_PROMPT, f"default negative lost {term!r}"


# --- what the user adds, on top of what the style already excludes ------
#
# The field reads as an override and was implemented as one. Someone who
# saw a mangled hand and typed "hands" got an image generated without
# "deformed", "bad anatomy", "extra fingers" or "crowd" — worse odds than
# leaving the box empty, and nothing about the result would say so.


def _scene_with(negative: str | None):
    from app.schemas.project import Scene, SceneAudio, SceneVisual

    return Scene(
        index=0,
        duration_s=4.0,
        visual=SceneVisual(prompt="a face", negative_prompt=negative),
        audio=SceneAudio(voiceover_line="line"),
    )


def test_a_scene_negative_adds_to_the_style_rather_than_replacing_it():
    from app.engines.visual_engine import negative_for

    style = ART_STYLES[0]
    combined = negative_for(_scene_with("hands, feet"), style)

    assert "hands" in combined and "feet" in combined
    for kept in ("deformed", "bad anatomy", "crowd", "extra fingers"):
        assert kept in combined, f"the style's {kept!r} was dropped"


def test_a_scene_that_adds_nothing_gets_the_style_untouched():
    from app.engines.visual_engine import negative_for

    style = ART_STYLES[0]

    assert negative_for(_scene_with(None), style) == style.negative_prompt
    assert negative_for(_scene_with("  "), style) == style.negative_prompt


def test_a_repeated_term_is_not_sent_twice():
    """The field is length-capped, so a duplicate costs room that a real
    term could have used."""
    from app.engines.visual_engine import negative_for

    style = ART_STYLES[0]
    combined = negative_for(_scene_with("Crowd, hands"), style)

    assert combined.lower().count("crowd") == 1
    assert "hands" in combined


def test_the_project_negative_reaches_every_scene():
    """Set once before the render, applied to all of them — including the
    scenes a re-roll will later start from."""
    from app.schemas.project import ProjectConfig

    config = ProjectConfig(topic="t", negative_prompt="hands, crowd")

    assert config.negative_prompt == "hands, crowd"


# --- the check that doesn't rely on the model remembering ---------------
#
# The rule above is followed most of the time. Three paid renders say what
# "most" means: six photographers with twelve unusable feet, a table of
# interlocking hands, and a close-up of feet on a dance floor — each one
# after the rule was already written. A fourth, firmer wording is not a
# plan, so this is the same answer visual_prompts_naming reached for the
# same reason.


def _scenes(*prompts: str) -> list[dict]:
    return [{"visual_prompt": p} for p in prompts]


@pytest.mark.parametrize(
    "prompt",
    [
        # The three that actually shipped.
        "a close-up of feet performing a simple dance step on a wooden floor",
        "a close-up of hands gesturing in conversation across a table, warm lighting",
        "a group of photographers at a fashion shoot, studio lights",
        # And the rest of the rule.
        "a full-body shot of a dancer mid-leap",
        "a woman lying down on a bed, soft morning light",
        "a crowd at a concert, hands in the air",
        "an audience watching a speaker",
    ],
)
def test_a_shot_the_model_cannot_draw_is_caught(prompt):
    from app.engines.script_engine import visual_prompts_framing

    assert visual_prompts_framing(_scenes(prompt)) == [0], prompt


@pytest.mark.parametrize(
    "prompt",
    [
        "a lively dance studio with mirrors, a person smiling, medium shot",
        "a medium shot of a dancer adding personal style while dancing",
        "a woman confidently walking in a lively urban street, close-up on her face",
        "a portrait of a person with an intense gaze, bright light",
        # Hands are in the frame and are not the subject. This is the
        # false positive a blunter matcher would produce, and it would
        # send perfectly good prompts through a rewrite that makes them
        # worse.
        "a close-up of someone writing in a notebook, soft light",
        "a woman walking, hands in her pockets, city street at dusk",
        "a jar of honey on a wooden table, warm side light",
    ],
)
def test_a_shot_that_works_is_left_alone(prompt):
    from app.engines.script_engine import visual_prompts_framing

    assert visual_prompts_framing(_scenes(prompt)) == [], prompt


def test_an_object_covered_in_numbers_is_caught():
    """A different failure from the text rule above, which forbids
    *describing* legible text. "a metronome ticking on a table" describes
    none — and came back with a dial reading 70, 20, 480, 1955, because
    the object carries the writing whether or not the prompt mentions it."""
    from app.engines.script_engine import visual_prompts_framing

    assert visual_prompts_framing(
        _scenes("a metronome ticking steadily on a table, soft focus background")
    ) == [0]


def test_every_bad_scene_is_reported_not_just_the_first():
    """The rewrite pass is batched, so a partial list would leave the rest
    in place and look like it worked."""
    from app.engines.script_engine import visual_prompts_framing

    scenes = _scenes(
        "a portrait of a woman by a window",
        "a close-up of hands on a keyboard",
        "a medium shot of a man reading",
        "a crowd of commuters on a platform",
    )

    assert visual_prompts_framing(scenes) == [1, 3]


# --- and what it does with what it finds ---------------------------------


async def test_a_caught_prompt_is_replaced(monkeypatch):
    from app.engines import script_engine as se

    async def fake_llm(config, system, user):
        assert "cannot draw" in system
        return '{"prompts": ["a dancer\'s face lit from the side, mid-movement"]}'

    monkeypatch.setattr(se, "_call_llm", fake_llm)
    parsed = {"scenes": _scenes(
        "a portrait of a woman by a window",
        "a close-up of feet on a wooden floor",
    )}

    await se._rewrite_badly_framed_prompts(parsed, object())

    assert parsed["scenes"][0]["visual_prompt"] == "a portrait of a woman by a window"
    assert "feet" not in parsed["scenes"][1]["visual_prompt"]


async def test_a_failed_rewrite_leaves_the_original(monkeypatch):
    """A badly framed prompt is what we already had, so a rewrite that
    errors must not also lose the scene."""
    from app.engines import script_engine as se

    async def explode(config, system, user):
        raise RuntimeError("model down")

    monkeypatch.setattr(se, "_call_llm", explode)
    parsed = {"scenes": _scenes("a close-up of feet on a wooden floor")}

    await se._rewrite_badly_framed_prompts(parsed, object())

    assert parsed["scenes"][0]["visual_prompt"] == "a close-up of feet on a wooden floor"


async def test_a_short_rewrite_is_refused_rather_than_misaligned(monkeypatch):
    """Two prompts sent, one returned. Zipping them would put the rewrite
    of the second onto the first."""
    from app.engines import script_engine as se

    async def one_back(config, system, user):
        return '{"prompts": ["only one"]}'

    monkeypatch.setattr(se, "_call_llm", one_back)
    parsed = {"scenes": _scenes(
        "a close-up of hands on a table",
        "a crowd at a concert",
    )}

    await se._rewrite_badly_framed_prompts(parsed, object())

    assert parsed["scenes"][0]["visual_prompt"] == "a close-up of hands on a table"
    assert parsed["scenes"][1]["visual_prompt"] == "a crowd at a concert"


async def test_nothing_is_called_when_every_prompt_is_fine(monkeypatch):
    """The pass costs an LLM round trip, so it must not fire on a script
    that had no problem."""
    from app.engines import script_engine as se

    called = False

    async def should_not_run(config, system, user):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(se, "_call_llm", should_not_run)
    parsed = {"scenes": _scenes("a portrait of a woman by a window")}

    await se._rewrite_badly_framed_prompts(parsed, object())

    assert called is False
