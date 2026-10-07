"""Where a beat edit's files live, and how an uploaded track is checked.

The clips and an uploaded track are written at fixed names inside the
project's own directory, numbered in upload order, so nothing a request
says can choose a path ffmpeg will open — the same rule `uploads` follows
for a single video. A library track is never copied: it is an id,
resolved against the music directory when the edit renders.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.services.uploads import ALLOWED_SUFFIXES, UploadRejected

MAX_CLIPS = 12
# Per file the upload cap applies (uploads.MAX_UPLOAD_BYTES); across the
# whole edit, this. Twelve phone clips at a minute each fit comfortably.
MAX_TOTAL_BYTES = 800 * 1024 * 1024
MAX_MUSIC_BYTES = 30 * 1024 * 1024

AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def clip_path(project_dir: Path, index: int, suffix: str) -> Path:
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".mp4"
    return project_dir / "source" / f"clip_{index:02d}{suffix}"


def clip_paths(project_dir: Path) -> list[Path]:
    return sorted((project_dir / "source").glob("clip_*"))


def music_path(project_dir: Path, suffix: str) -> Path:
    if suffix not in AUDIO_SUFFIXES:
        suffix = ".mp3"
    return project_dir / "source" / f"music{suffix}"


def uploaded_music(project_dir: Path) -> Path | None:
    found = sorted((project_dir / "source").glob("music.*"))
    return found[0] if found else None


def base_path(project_dir: Path) -> Path:
    """The finished edit with nothing written over it — what the editor
    burns text onto, so a second edit does not stack on the first."""
    return project_dir / "output" / "edit_base.mp4"


async def probe_audio(path: Path, ffprobe_binary: str = "ffprobe") -> float:
    """The track's length in seconds, or a refusal if it has no audio."""
    proc = await asyncio.create_subprocess_exec(
        ffprobe_binary, "-v", "error", "-show_entries",
        "format=duration:stream=codec_type", "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise UploadRejected("That music file could not be read.")
    try:
        data = json.loads(stdout.decode())
    except json.JSONDecodeError as exc:
        raise UploadRejected("That music file could not be read.") from exc
    if not any(s.get("codec_type") == "audio" for s in data.get("streams") or []):
        raise UploadRejected("That music file has no audio in it.")
    try:
        return float((data.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0
