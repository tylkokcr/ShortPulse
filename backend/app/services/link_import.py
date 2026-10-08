"""Bring a video in from a link instead of from the user's disk.

Two kinds of link, with very different standing:

* **A file the user already has somewhere** — Google Drive, Dropbox,
  OneDrive (personal and work), Box, or a plain link to a video
  file. Fetching it is no different from the user
  uploading it, just without pushing a gigabyte up a phone connection.

* **A YouTube video.** YouTube offers no API for downloading a video, its
  terms forbid automated downloading, and its servers increasingly refuse
  datacenter addresses. So this is off unless the operator turns it on
  (`youtube_import_enabled`), the user must confirm they hold the rights
  to the video, the downloaded source expires after a day, and a project
  made from it is never posted through our YouTube (or any) connection —
  re-uploading a downloaded YouTube video through YouTube's own API is the
  one use that would put the app's API access at risk. Content ID on the
  user's own upload still applies, as it does to anything.

Either way the result is an ordinary file in My files, so every flow that
takes a file — captions, dubbing, clips, beat edits — takes this one too.

The plain-link fetch is where the security is. A URL from a request is
fetched by this server, so it must not be able to reach this server's own
network: every hop of every redirect is resolved and refused unless all of
its addresses are public (`_check_public`).
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import re
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

from app.services.uploads import UploadRejected

logger = logging.getLogger(__name__)

_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be",
}
_MAX_REDIRECTS = 5
_YOUTUBE_FORMATS = (
    "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/b[height<=1080][vcodec^=avc1]",
    "bv*[height<=1080]+ba/b[height<=1080]/b",
)
_CHUNK = 1 << 20


@dataclass(frozen=True)
class Link:
    kind: str  # "youtube" | "direct"
    url: str
    #: A name to show in My files before the file says otherwise.
    name: str


def classify(raw: str) -> Link:
    """What a pasted link is, and the URL to fetch for it. Raises
    UploadRejected for anything that is not an http(s) link."""
    url = raw.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UploadRejected("That doesn't look like a link. Paste the whole address.")
    host = parsed.hostname.lower()

    if host in _YOUTUBE_HOSTS:
        video_id = None
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.path.startswith(("/shorts/", "/live/")):
            video_id = parsed.path.split("/")[2]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0] or None
        if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
            raise UploadRejected("That YouTube link doesn't point at a single video.")
        return Link("youtube", f"https://www.youtube.com/watch?v={video_id}", f"YouTube {video_id}")

    name = Path(parsed.path).name or host
    # Share links, rewritten to the address that serves the file itself.
    if host == "drive.google.com":
        match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
        file_id = match.group(1) if match else parse_qs(parsed.query).get("id", [""])[0]
        if not file_id:
            raise UploadRejected("That Google Drive link doesn't point at a file.")
        return Link(
            "direct",
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
            "Google Drive video",
        )
    if host in ("www.dropbox.com", "dropbox.com"):
        query = parse_qs(parsed.query)
        query.pop("dl", None)
        query["dl"] = ["1"]
        rebuilt = "&".join(f"{k}={v[0]}" for k, v in query.items())
        return Link("direct", urlunparse(parsed._replace(query=rebuilt)), name)
    # OneDrive (personal): any share link, encoded into the shares API,
    # which answers with the file itself.
    if host in ("1drv.ms", "onedrive.live.com"):
        token = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        return Link(
            "direct", f"https://api.onedrive.com/v1.0/shares/u!{token}/root/content", "OneDrive video"
        )
    # OneDrive for work and SharePoint: the share link downloads when asked.
    if host.endswith(".sharepoint.com"):
        query = parse_qs(parsed.query)
        query["download"] = ["1"]
        rebuilt = "&".join(f"{k}={v[0]}" for k, v in query.items())
        return Link("direct", urlunparse(parsed._replace(query=rebuilt)), name)
    # Box: a /s/<name> share link is served raw under /shared/static/<name>.
    if host == "app.box.com" or host.endswith(".app.box.com") or host.endswith(".box.com"):
        match = re.match(r"/s/([A-Za-z0-9]+)", parsed.path)
        if match:
            return Link(
                "direct", f"https://{host}/shared/static/{match.group(1)}", "Box video"
            )
    return Link("direct", url, name)


def _check_public(url: str) -> None:
    """Refuse a URL whose host resolves to anything but public addresses —
    loopback, the private ranges, link-local (cloud metadata lives there),
    and the rest. Checked per hop, because a public page can redirect to
    a private one."""
    host = urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UploadRejected("That link's address could not be found.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UploadRejected("That link points somewhere this server won't fetch from.")


async def fetch_direct(url: str, destination: Path, cap_bytes: int) -> int:
    """Stream a plain link to `destination`, following redirects by hand
    so each hop is checked. Returns the bytes written."""
    current = url
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0)) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            await asyncio.to_thread(_check_public, current)
            async with client.stream("GET", current, follow_redirects=False) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise UploadRejected("That link redirects nowhere.")
                    current = str(response.url.join(location))
                    continue
                if response.status_code >= 400:
                    raise UploadRejected(
                        f"That link answered {response.status_code}. Is it shared publicly?"
                    )
                kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind.startswith("text/html"):
                    # A sign-in page, a preview page, a "file too large to
                    # scan" page: anything but the file.
                    raise UploadRejected(
                        "That link opens a web page, not a video file. Share it so "
                        "anyone with the link can download it."
                    )
                length = int(response.headers.get("content-length") or 0)
                if length > cap_bytes:
                    raise UploadRejected("That video is larger than the upload limit.")
                written = 0
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as out:
                    async for chunk in response.aiter_bytes(_CHUNK):
                        written += len(chunk)
                        if written > cap_bytes:
                            raise UploadRejected("That video is larger than the upload limit.")
                        out.write(chunk)
                return written
    raise UploadRejected("That link redirects too many times.")


def fetch_youtube(url: str, destination: Path, cap_bytes: int, max_s: float, ffmpeg: str) -> str:
    """Download one YouTube video, at most 1080p, as an mp4 at
    `destination`. Returns its title. Blocking; run it in a thread."""
    import yt_dlp  # type: ignore[import-untyped]

    def too_long(info, *, incomplete):  # noqa: ARG001 - yt-dlp's signature
        duration = info.get("duration")
        if info.get("is_live"):
            return "a live stream can't be imported"
        if duration and duration > max_s:
            return "too long"
        return None

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as work:
        base = {
            "merge_output_format": "mp4",
            "outtmpl": str(Path(work) / "video.%(ext)s"),
            "noplaylist": True,
            "max_filesize": cap_bytes,
            "match_filter": too_long,
            "retries": 3,
            "fragment_retries": 3,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "ffmpeg_location": ffmpeg,
        }
        info = None
        last: Exception | None = None
        # H.264 first — every ffmpeg decodes it and it cuts fastest — then
        # whatever YouTube serves at up to 1080p (VP9, AV1). One stream
        # failing mid-download with a 403 was seen in testing and passed on
        # a second try, so the looser choice is the retry.
        for fmt in _YOUTUBE_FORMATS:
            try:
                with yt_dlp.YoutubeDL({**base, "format": fmt}) as ydl:
                    info = ydl.extract_info(url, download=True)
                break
            except yt_dlp.utils.DownloadError as exc:
                last = exc
                for partial in Path(work).glob("video.*"):
                    partial.unlink(missing_ok=True)
                if "too long" in str(exc) or "live stream" in str(exc):
                    break
        if info is None:
            message = str(last or "")
            logger.warning("YouTube import of %s failed: %s", url, message)
            if "too long" in message:
                raise UploadRejected(f"That video is longer than {int(max_s // 3600)} hours.")
            if "live stream" in message:
                raise UploadRejected("A live stream can't be brought in. Try once it has ended.")
            if "Sign in" in message or "bot" in message:
                raise UploadRejected(
                    "YouTube refused this server just now. Try again later, or download "
                    "the video and upload the file."
                )
            raise UploadRejected("That YouTube video couldn't be downloaded.")
        files = sorted(Path(work).glob("video.*"))
        if info is None or not files:
            raise UploadRejected("That YouTube video couldn't be downloaded.")
        files[0].replace(destination)
        return str(info.get("title") or "YouTube video")[:200]
