"""Aspect ratio resolution.

`ProjectConfig.aspect_ratio` was accepted, validated and persisted for
every project while nothing in the pipeline ever read it — the render
target came straight from `settings.default_resolution`, so a request for
1:1 or 16:9 produced a 9:16 video with no error anywhere. These pin the
mapping so it can't quietly revert to that.
"""

from __future__ import annotations

import pytest

from app.schemas.project import AspectRatio
from app.services.render_manager import resolution_for

DEFAULT = (1080, 1920)


@pytest.mark.parametrize(
    ("aspect_ratio", "expected"),
    [
        (AspectRatio.VERTICAL_9_16, (1080, 1920)),
        (AspectRatio.SQUARE_1_1, (1080, 1080)),
        (AspectRatio.HORIZONTAL_16_9, (1920, 1080)),
    ],
)
def test_maps_to_the_sizes_platforms_expect(aspect_ratio, expected):
    assert resolution_for(aspect_ratio, DEFAULT) == expected


def test_each_ratio_is_distinct():
    """The regression itself: every ratio returning the same size."""
    sizes = {resolution_for(ratio, DEFAULT) for ratio in AspectRatio}
    assert len(sizes) == len(list(AspectRatio))


@pytest.mark.parametrize("aspect_ratio", list(AspectRatio))
def test_dimensions_are_even(aspect_ratio):
    """H.264 with yuv420p cannot encode odd dimensions."""
    width, height = resolution_for(aspect_ratio, (1079, 1919))
    assert width % 2 == 0
    assert height % 2 == 0


def test_unknown_ratio_falls_back_to_the_default():
    assert resolution_for("21:9", DEFAULT) == DEFAULT
