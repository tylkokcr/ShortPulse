"""The background-music library.

Tracks are whatever audio files sit in `app/assets/music`, discovered at
request time rather than hardcoded — dropping a file into that directory
is all it takes to offer it, and deleting one can't leave the UI pointing
at a path that no longer exists.

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
    back to a real path only by `track_path_for`."""

    id: str
    name: str


def _music_dir() -> Path:
    return get_settings().default_music_track_path.parent


def available_tracks() -> list[Track]:
    directory = _music_dir()
    if not directory.is_dir():
        return []
    return [
        Track(id=path.stem, name=path.stem)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() in _AUDIO_SUFFIXES
    ]


def track_path_for(track_id: str) -> Path:
    """Resolve a track id to a path inside the music directory.

    Rejects anything that escapes it, so an id like `../../etc/passwd`
    cannot reach ffmpeg.
    """
    directory = _music_dir().resolve()
    for path in directory.iterdir() if directory.is_dir() else []:
        if path.is_file() and path.suffix.lower() in _AUDIO_SUFFIXES and path.stem == track_id:
            resolved = path.resolve()
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
