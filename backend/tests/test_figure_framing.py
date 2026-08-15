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
