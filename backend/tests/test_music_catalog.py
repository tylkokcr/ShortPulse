"""The music library, and the ids that reach ffmpeg.

Two things matter here and they pull in opposite directions. The catalog
is deliberately just a directory — dropping a file in is all it takes to
offer it, with no manifest to keep in step — and `MusicConfig.track_path`
is fed straight to ffmpeg, so an id that could name a file outside that
directory would hand a caller any file on the box, mixed into a video they
can then download.
"""

from __future__ import annotations

import pytest

from app.api.routes import music
from app.core.config import get_settings


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A music directory with moods, a top-level file, and a decoy."""
    for mood, names in {
        "lofi": ["Birds", "Tokyo Sunset"],
        "upbeat": ["Sweet Sun"],
    }.items():
        (tmp_path / mood).mkdir()
        for name in names:
            (tmp_path / mood / f"{name}.mp3").write_bytes(b"id3")
    (tmp_path / "Airport Lounge.mp3").write_bytes(b"id3")
    (tmp_path / "lofi" / "notes.txt").write_text("not audio")
    # Sits next to the library, so a traversal would reach it.
    (tmp_path.parent / "secret.mp3").write_bytes(b"private")

    monkeypatch.setattr(get_settings(), "default_music_track_path", tmp_path / "Airport Lounge.mp3")
    return tmp_path


def test_a_subdirectory_is_a_mood(library):
    tracks = {t.id: t.category for t in music.available_tracks()}

    assert tracks["Birds"] == "lofi"
    assert tracks["Sweet Sun"] == "upbeat"


def test_a_top_level_file_has_no_category(library):
    """Where the bundled default lives — it belongs to no mood and should
    not invent one."""
    tracks = {t.id: t.category for t in music.available_tracks()}

    assert tracks["Airport Lounge"] is None


def test_non_audio_is_ignored(library):
    """ATTRIBUTION.md sits in this directory and is not a track."""
    assert "notes" not in {t.id for t in music.available_tracks()}


def test_the_listing_is_stable(library):
    """Filesystems do not promise iteration order, and a picker that
    reshuffles itself between requests is unusable."""
    assert [t.id for t in music.available_tracks()] == [
        t.id for t in music.available_tracks()
    ]


def test_an_id_resolves_to_the_file_it_names(library):
    assert music.track_path_for("Birds").name == "Birds.mp3"
    assert music.track_path_for("Airport Lounge").name == "Airport Lounge.mp3"


def test_a_traversal_is_refused(library):
    """The id reaches ffmpeg as a path. Matching against a listing rather
    than joining is what makes that safe, and this pins it."""
    from fastapi import HTTPException

    for attempt in ("../secret", "../../etc/passwd", "/etc/passwd", "lofi/Birds"):
        with pytest.raises(HTTPException) as caught:
            music.track_path_for(attempt)
        assert caught.value.status_code == 404


def test_an_unknown_id_is_a_404_not_a_crash(library):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        music.track_path_for("Nothing By That Name")
