"""Art style catalog.

The styles exist to hide what diffusion gets wrong at this size — faces,
hands, on-screen text — so the ones that matter are the non-photoreal
entries. Two things here are worth pinning:

  * The style must lead the prompt. Appended as a suffix, "3D Toon" and
    "Claymation" rendered as ordinary photographs against the photoreal
    default checkpoint; moving the style to the front fixed both. A
    template that puts `{prompt}` first would silently undo that.
  * A stylized negative prompt must not suppress the very thing it asks
    for. The shared negative bans "3d render" and "illustration", which
    would fight an anime or toon render.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import art_styles

FRONTEND_SAMPLES = (
    Path(__file__).resolve().parents[2] / "frontend" / "public" / "art-styles"
)


def test_ids_are_unique():
    ids = [style.id for style in art_styles.ART_STYLES]
    assert len(ids) == len(set(ids))


def test_default_is_photoreal():
    assert art_styles.DEFAULT_ART_STYLE.id == "photoreal"


def test_unknown_id_falls_back_rather_than_raising():
    """A charged render should degrade to the default look, not fail."""
    assert art_styles.by_id("no-such-style") is art_styles.DEFAULT_ART_STYLE
    assert art_styles.by_id(None) is art_styles.DEFAULT_ART_STYLE
    assert art_styles.by_id("") is art_styles.DEFAULT_ART_STYLE


@pytest.mark.parametrize("style", art_styles.ART_STYLES, ids=lambda s: s.id)
def test_template_substitutes_the_subject(style):
    built = style.build_prompt("a red bicycle")
    assert "a red bicycle" in built
    assert "{prompt}" not in built


@pytest.mark.parametrize(
    "style", [s for s in art_styles.ART_STYLES if s.id != "photoreal"], ids=lambda s: s.id
)
def test_stylized_styles_lead_with_the_style(style):
    """`{prompt}` late in the template is what makes the style stick."""
    position = style.prompt_template.index("{prompt}")
    assert position > 40, f"{style.id}: subject appears too early to weight the style"


@pytest.mark.parametrize(
    "style", [s for s in art_styles.ART_STYLES if s.id != "photoreal"], ids=lambda s: s.id
)
def test_stylized_negatives_do_not_ban_being_stylized(style):
    """e.g. an anime style whose negative prompt contains "illustration"."""
    negative = style.negative_prompt.lower()
    for banned in ("illustration", "cartoon", "anime", "stylized"):
        assert banned not in negative, f"{style.id} suppresses {banned!r}"


@pytest.mark.parametrize("style", art_styles.ART_STYLES, ids=lambda s: s.id)
def test_every_style_ships_a_sample_image(style):
    """The picker shows these; a missing file is a broken card."""
    assert (FRONTEND_SAMPLES / style.sample).is_file()
