"""The cut emphasis, as an ffmpeg expression.

A generated scene used to be a still frame held for as long as the line
took to say. Whatever the picture was, four seconds of it without a move
reads as a slideshow — which is the specific complaint this answers.

Stills were never the problem: `_render_image_scene_clip` has always had
Ken Burns. Stock and AI-video clips had nothing at all, and those are
what this touches.

The expression is the behaviour here, so these assert on it — plus the
two properties that are easy to get wrong and invisible in code review:
the zoom has to settle exactly back to 1, and it has to hold the centre
rather than pulling toward a corner.
"""

from __future__ import annotations

import pytest

from app.engines.render_engine import PUNCH_S, PUNCH_ZOOMS, RenderTarget, punch_filter

TARGET = RenderTarget(1080, 1920, 25)


def test_the_zoom_settles_back_to_one():
    """Anything else leaves every scene permanently cropped tighter than
    the one before it — and on stock footage that means losing the edges
    of a shot somebody chose."""
    expression = punch_filter(0, TARGET, 3.0)

    assert f"lt(it,{PUNCH_S})" in expression
    # The false branch of the conditional, which is what runs for all but
    # the first third of a second.
    assert expression.count(",1)'") == 1


def test_the_centre_is_held():
    """zoompan's x and y default to 0, which zooms into the top-left
    corner — the subject slides out of frame as the punch lands."""
    expression = punch_filter(0, TARGET, 3.0)

    assert "x='iw/2-(iw/zoom/2)'" in expression
    assert "y='ih/2-(ih/zoom/2)'" in expression


def test_one_output_frame_per_input_frame():
    """`d` is how many frames zoompan emits per input frame. Its default
    of 25 is right for a still and turns a video into a slideshow of
    every 25th frame."""
    assert "d=1" in punch_filter(0, TARGET, 3.0)


def test_the_output_size_and_rate_follow_the_target():
    expression = punch_filter(0, TARGET, 3.0)

    assert "s=1080x1920" in expression
    assert "fps=25" in expression


def test_consecutive_scenes_do_not_punch_identically():
    """Six scenes with the same move at the same moment ticks like a
    metronome, which is its own kind of cheap."""
    first = punch_filter(0, TARGET, 3.0)
    second = punch_filter(1, TARGET, 3.0)

    assert first != second


def test_the_pattern_repeats_rather_than_growing():
    """Alternating, not escalating — scene nine must not be zoomed twice
    as far in as scene one."""
    assert punch_filter(0, TARGET, 3.0) == punch_filter(len(PUNCH_ZOOMS), TARGET, 3.0)


@pytest.mark.parametrize("index", range(6))
def test_every_scene_starts_zoomed_in_and_never_out(index):
    """A punch that starts below 1 is a zoom *out*, which reveals the
    edges of the frame — on a clip already cropped to fill, that is black
    bars."""
    assert all(zoom > 1 for zoom in PUNCH_ZOOMS)
    assert "1+0." in punch_filter(index, TARGET, 3.0)
