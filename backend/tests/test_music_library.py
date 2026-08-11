"""Music track resolution.

`MusicConfig.track_path` is passed to ffmpeg as an input file. It used to
be settable straight from the request body, which made it an
arbitrary-file-read primitive: an authenticated caller could name any file
the server could open and have ffmpeg mix it into a video they then
downloaded. Clients now send an opaque `track_id` and the server resolves
it against the music directory; these pin that boundary.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.music import available_tracks, track_path_for


def test_lists_the_bundled_track():
    names = [track.id for track in available_tracks()]
    assert "Airport Lounge" in names


def test_resolves_a_real_track_inside_the_music_directory():
    path = track_path_for("Airport Lounge")
    assert path.is_file()
    assert path.parent.name == "music"


@pytest.mark.parametrize(
    "track_id",
    [
        "../../../../etc/passwd",
        "../../core/config",
        "/etc/passwd",
        "does-not-exist",
        "",
    ],
)
def test_refuses_anything_outside_the_library(track_id):
    with pytest.raises(HTTPException) as exc:
        track_path_for(track_id)
    assert exc.value.status_code == 404
