"""Storage and validation for user-supplied source video.

This is the one place the product accepts a file from the outside world,
so the rules are all here rather than spread through the route:

  * The client's filename is never used. It is attacker-controlled and
    ends up in a path — the only safe treatment is to discard it and
    derive the name from the project id, which the server minted. This is
    the same rule the music library follows (`music.track_path_for`).
  * The declared size is never trusted. `Content-Length` is a claim, so
    the cap is enforced while streaming and the partial file is deleted
    the moment it is exceeded.
  * The declared type is never trusted either. A `.mp4` extension and a
    `video/mp4` content-type cost nothing to forge, so acceptance depends
    on ffprobe actually finding a decodable video stream.

Nothing here hands a client-supplied string to ffmpeg.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Roughly a 10-minute 1080p phone recording. The product makes short-form
# video; anything much larger is a misunderstanding of what it does, and
# the cost of finding that out is a full upload plus a Whisper pass.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

# Read size for the streaming copy. Large enough not to syscall per
# kilobyte, small enough that the cap is enforced promptly.
CHUNK_BYTES = 1024 * 1024

# Container formats ffmpeg reads reliably and browsers can play back. The
# extension is only used to name our own file — it is not what decides
# whether the upload is accepted.
ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


class UploadRejected(ValueError):
    """The file is not something we can or will process."""


@dataclass(frozen=True)
class ProbedMedia:
    duration_s: float
    width: int
    height: int
    has_audio: bool


def source_path_for(project_dir_path: Path, suffix: str = ".mp4") -> Path:
    """Where a project's uploaded source lives.

    Derived entirely from the project directory the server chose. A caller
    cannot influence it, which is the point: the result is passed to
    ffmpeg.
    """
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".mp4"
    return project_dir_path / "source" / f"source{suffix}"


async def save_stream(chunks, destination: Path, max_bytes: int = MAX_UPLOAD_BYTES) -> int:
    """Stream an upload to disk, enforcing the cap as it goes.

    Returns the number of bytes written. Raises UploadRejected — having
    already removed the partial file — if the cap is passed, so a client
    cannot fill the disk by lying about Content-Length or by sending a
    chunked body with no length at all.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with destination.open("wb") as out:
            async for chunk in chunks:
                written += len(chunk)
                if written > max_bytes:
                    raise UploadRejected(
                        f"File is larger than the {max_bytes // (1024 * 1024)}MB limit"
                    )
                out.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise

    if written == 0:
        destination.unlink(missing_ok=True)
        raise UploadRejected("File is empty")
    return written


async def probe(path: Path, ffprobe_binary: str = "ffprobe") -> ProbedMedia:
    """Confirm the file really is video, and report what it contains.

    Acceptance rests on this rather than on the filename or the declared
    content-type, both of which the client controls. A renamed archive or
    a text file gets no further than here.
    """
    cmd = [
        ffprobe_binary,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise UploadRejected(
            "That file could not be read as video. "
            f"({stderr.decode(errors='ignore').strip()[:200]})"
        )

    try:
        data = json.loads(stdout.decode())
    except json.JSONDecodeError as exc:
        raise UploadRejected("That file could not be read as video.") from exc

    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise UploadRejected("That file has no video track.")

    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise UploadRejected("That file has no playable duration.")

    return ProbedMedia(
        duration_s=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )
