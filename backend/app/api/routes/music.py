"""The background-music library.

Tracks are whatever audio files sit in `app/assets/music`, discovered at
request time rather than hardcoded — dropping a file into that directory
is all it takes to offer it, and deleting one can't leave the UI pointing
at a path that no longer exists.

A subdirectory is a mood: `music/lofi/Birds.mp3` is a lo-fi track called
Birds. That keeps the "no manifest to maintain" property while making a
list of forty usable — the alternative was a JSON file mapping ids to
categories, which is one more thing that can disagree with what is on
disk. Files at the top level have no category and are listed last, which
is where the bundled default lives.

Only a name and an opaque id go over the wire. The absolute path stays
server-side: `MusicConfig.track_path` is fed straight to ffmpeg, so
accepting one from the client would let a caller name any file on the box
and have it mixed into a video they can then download.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/music", tags=["music"])

_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"}


class Track(BaseModel):
    """`id` is the filename stem — stable across restarts, and resolved
    back to a real path only by `track_path_for`.

    Not the path: an id has to survive a track being re-filed under a
    different mood without invalidating anything that stored it, and it
    has to be something a URL can carry.
    """

    id: str
    name: str
    # The subdirectory it came from, or None for a top-level file.
    category: str | None = None


def _music_dir() -> Path:
    return get_settings().default_music_track_path.parent


def _audio_files(directory: Path) -> list[Path]:
    """Every track, one level deep. Sorted so the list is stable across
    filesystems that don't iterate in order."""
    if not directory.is_dir():
        return []
    found = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _AUDIO_SUFFIXES]
    for sub in sorted(p for p in directory.iterdir() if p.is_dir()):
        found.extend(
            p for p in sorted(sub.iterdir())
            if p.is_file() and p.suffix.lower() in _AUDIO_SUFFIXES
        )
    return found


def available_tracks() -> list[Track]:
    directory = _music_dir()
    return [
        Track(
            id=path.stem,
            name=path.stem,
            category=path.parent.name if path.parent != directory else None,
        )
        for path in sorted(_audio_files(directory), key=lambda p: (p.parent.name, p.stem))
    ]


def track_path_for(track_id: str) -> Path:
    """Resolve a track id to a path inside the music directory.

    Rejects anything that escapes it, so an id like `../../etc/passwd`
    cannot reach ffmpeg.
    """
    directory = _music_dir().resolve()
    for path in _audio_files(directory):
        if path.stem == track_id:
            resolved = path.resolve()
            # Belt and braces: the id was matched against a listing rather
            # than joined onto a path, so it cannot contain a traversal —
            # but this is the function that hands a path to ffmpeg, and it
            # should not depend on the caller above staying that way.
            if resolved.is_relative_to(directory):
                return resolved
    raise HTTPException(status_code=404, detail=f"No such track: {track_id!r}")


@router.get("", response_model=list[Track])
async def list_tracks() -> list[Track]:
    return available_tracks()


@router.get("/preview")
async def preview(track_id: str = Query(..., description="Track id from GET /api/music")):
    """The track itself, for auditioning before a render.

    A list of filenames is not a choice anyone can make. Music is the one
    setting whose effect cannot be described — "Airport Lounge" tells a
    user nothing about whether it suits their video — so the catalog is
    only useful if it can be heard, and adding tracks to it is only worth
    doing once it can.

    Served whole rather than trimmed. A shortened preview would need
    transcoding and a cache, and the honest reason not to is that the
    thing being auditioned is a loop under a voiceover: the first fifteen
    seconds are the decision, and the browser stops fetching when the
    element is paused. Range requests are handled by FileResponse, so
    seeking works without pulling the file twice.

    `track_path_for` is what makes this safe to expose: an id is resolved
    against the music directory and anything escaping it is a 404, so this
    cannot be turned into a file reader.
    """
    path = track_path_for(track_id)
    return FileResponse(
        path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
