"""Editing a finished video.

The property that makes this feature affordable is that an edit re-runs
the burn-in pass and nothing else. These pin the two things that would
quietly break it: drawing onto footage that already has captions on it,
and letting user-typed text reach libass unescaped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engines import subtitle_engine
from app.schemas.project import (
    CaptionTrack,
    OverlayPosition,
    Project,
    ProjectConfig,
    SubtitleStyle,
    TextOverlay,
    Word,
)
from app.services import editing


def _project(tmp_path: Path, source: str | None = None) -> Project:
    return Project(config=ProjectConfig(topic="t"), source_path=source)


def test_reburn_starts_from_the_uploaded_source_when_there_is_one(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")

    assert editing.burn_source_for(_project(tmp_path, str(source))) == source


def test_reburn_never_starts_from_the_captioned_output(tmp_path, monkeypatch):
    """final.mp4 already has captions burned in. Drawing a corrected track
    over it would leave both on screen — the bug this guards is invisible
    until you watch the result."""
    project = _project(tmp_path)
    paths = tmp_path / project.config.id
    (paths / "output").mkdir(parents=True)
    (paths / "output" / "final.mp4").write_bytes(b"final")
    (paths / "output" / "concatenated.mp4").write_bytes(b"pre-subtitles")
    monkeypatch.setattr(editing, "project_dir", lambda _id: paths)

    chosen = editing.burn_source_for(project)

    assert chosen.name == "concatenated.mp4"


def test_a_project_with_no_footage_left_says_so(tmp_path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(editing, "project_dir", lambda _id: tmp_path / "missing")

    with pytest.raises(editing.NothingToReburn):
        editing.burn_source_for(project)


def test_a_missing_upload_falls_back_rather_than_failing(tmp_path, monkeypatch):
    """The recorded path can go stale — storage moves, a file is pruned.
    A generated project still has its pre-subtitle concat to fall back on."""
    project = _project(tmp_path, str(tmp_path / "gone.mp4"))
    paths = tmp_path / project.config.id
    (paths / "output").mkdir(parents=True)
    (paths / "output" / "concatenated.mp4").write_bytes(b"pre-subtitles")
    monkeypatch.setattr(editing, "project_dir", lambda _id: paths)

    assert editing.burn_source_for(project).name == "concatenated.mp4"


# --------------------------------------------------------------------------
# Overlay rendering
# --------------------------------------------------------------------------


def _ass(tmp_path, overlays, words=None) -> str:
    path = subtitle_engine.build_ass_from_words(
        words or [Word(text="hello", start_ms=0, end_ms=500)],
        SubtitleStyle(),
        tmp_path / "captions.ass",
        play_res=(1080, 1920),
        overlays=overlays,
    )
    return path.read_text()


def test_an_overlay_becomes_an_event_above_the_caption_layer(tmp_path):
    body = _ass(
        tmp_path,
        [TextOverlay(text="TITLE", start_ms=500, end_ms=2000, position=OverlayPosition.TOP)],
    )

    assert "Dialogue: 1,0:00:00.50,0:00:02.00" in body
    assert "\\an8" in body
    assert "TITLE" in body
    # Captions stay on layer 0, so the overlay draws over them.
    assert "Dialogue: 0," in body


def test_braces_in_user_text_cannot_open_an_override_block(tmp_path):
    """A brace doesn't render wrong, it starts a formatting block and eats
    the rest of the line. This is typed by the user, so it is reachable.

    The guarantee is about structure, not about the characters: with the
    braces gone, `\\c&HFF0000&` is just text libass draws. So what's
    asserted is that the event carries exactly one override block — the one
    this module wrote — and the user's contribution is all outside it.
    """
    body = _ass(tmp_path, [TextOverlay(text="{\\c&HFF0000&}pwned", start_ms=0, end_ms=1000)])
    event = next(ln for ln in body.splitlines() if ln.startswith("Dialogue: 1,"))
    text = event.split(",,", 1)[1]

    assert "pwned" in text
    assert text.count("{") == 1 and text.count("}") == 1
    assert text.index("}") < text.index("pwned"), "user text ended up inside the tag block"


def test_a_newline_cannot_forge_a_second_event(tmp_path):
    body = _ass(tmp_path, [TextOverlay(text="a\nDialogue: 0,junk", start_ms=0, end_ms=1000)])

    assert len([ln for ln in body.splitlines() if ln.startswith("Dialogue: 1,")]) == 1


def test_a_zero_length_or_empty_overlay_is_dropped(tmp_path):
    body = _ass(
        tmp_path,
        [
            TextOverlay(text="never", start_ms=1000, end_ms=1000),
            TextOverlay(text="   ", start_ms=0, end_ms=500),
        ],
    )

    assert "Dialogue: 1," not in body
    assert "never" not in body


def test_positions_map_to_the_right_alignment(tmp_path):
    for position, code in (
        (OverlayPosition.TOP, "\\an8"),
        (OverlayPosition.MIDDLE, "\\an5"),
        (OverlayPosition.BOTTOM, "\\an2"),
    ):
        body = _ass(tmp_path, [TextOverlay(text="x", start_ms=0, end_ms=1, position=position)])
        assert code in body, position


def test_a_caption_track_survives_a_round_trip_through_the_model():
    track = CaptionTrack(words=[Word(text="pH", start_ms=0, end_ms=100)])
    assert CaptionTrack.model_validate(track.model_dump()).words[0].text == "pH"
