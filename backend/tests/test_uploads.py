"""Accepting a video from the outside world.

This is the only endpoint that takes a file from a client, so most of what
is pinned here is what happens when the file is not what it claims to be.
The upload is written to disk and then handed to ffmpeg, which makes the
usual two mistakes expensive: trusting the client's filename (it becomes a
path) and trusting the declared size (it becomes disk).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services import uploads

FFPROBE = os.environ.get("FFPROBE_BINARY") or shutil.which("ffprobe") or "ffprobe"
FFMPEG = os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg") or "ffmpeg"

pytestmark = pytest.mark.skipif(
    shutil.which(FFPROBE) is None and not Path(FFPROBE).exists(),
    reason=f"{FFPROBE} not available",
)


async def _stream(data: bytes, chunk: int = 1024):
    for i in range(0, len(data), chunk):
        yield data[i : i + chunk]


def _real_video(path: Path, seconds: float = 1.0, with_audio: bool = True) -> Path:
    args = [
        FFMPEG, "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={seconds}:r=30",
    ]
    if with_audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest"]
    if with_audio:
        args += ["-c:a", "aac"]
    args += [str(path)]
    subprocess.run(args, capture_output=True, check=True)
    return path


# --------------------------------------------------------------------------
# Path derivation — the client's filename must never reach the filesystem
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile_suffix",
    [
        "/../../../../etc/passwd",
        "/../../secrets.env",
        ".mp4/../../../../tmp/pwned",
        "",
        ".sh",
        ".exe",
    ],
)
def test_the_stored_path_never_escapes_the_project_directory(tmp_path, hostile_suffix):
    """The name is derived from the project directory the server chose, so
    there is nothing in it for a caller to influence."""
    destination = uploads.source_path_for(tmp_path, hostile_suffix)

    assert destination.parent.parent == tmp_path
    assert destination.name.startswith("source")
    assert tmp_path in destination.resolve().parents


def test_an_unknown_extension_falls_back_to_mp4(tmp_path):
    assert uploads.source_path_for(tmp_path, ".sh").suffix == ".mp4"


def test_a_known_container_keeps_its_extension(tmp_path):
    assert uploads.source_path_for(tmp_path, ".mov").suffix == ".mov"


# --------------------------------------------------------------------------
# Size cap — enforced while streaming, not from the declared length
# --------------------------------------------------------------------------


async def test_a_file_over_the_cap_is_rejected_and_not_left_on_disk(tmp_path):
    """Content-Length is a claim. A client can understate it, or send a
    chunked body with no length at all, so the cap has to hold against the
    bytes actually arriving."""
    destination = tmp_path / "source" / "source.mp4"

    with pytest.raises(uploads.UploadRejected, match="larger than"):
        await uploads.save_stream(_stream(b"x" * 5000), destination, max_bytes=1000)

    assert not destination.exists(), "the partial upload was left behind"


async def test_an_empty_file_is_rejected(tmp_path):
    destination = tmp_path / "source" / "source.mp4"
    with pytest.raises(uploads.UploadRejected, match="empty"):
        await uploads.save_stream(_stream(b""), destination)
    assert not destination.exists()


async def test_a_file_within_the_cap_is_written_whole(tmp_path):
    destination = tmp_path / "source" / "source.mp4"
    written = await uploads.save_stream(_stream(b"x" * 4096), destination, max_bytes=8192)

    assert written == 4096
    assert destination.read_bytes() == b"x" * 4096


# --------------------------------------------------------------------------
# Content validation — the extension and content-type are not evidence
# --------------------------------------------------------------------------


async def test_a_renamed_non_video_is_rejected(tmp_path):
    """The classic: a zip named .mp4. Only ffprobe's opinion counts."""
    fake = tmp_path / "source.mp4"
    fake.write_bytes(b"PK\x03\x04" + b"\x00" * 2048)

    with pytest.raises(uploads.UploadRejected):
        await uploads.probe(fake, FFPROBE)


async def test_a_text_file_is_rejected(tmp_path):
    fake = tmp_path / "source.mp4"
    fake.write_text("this is not a video" * 100)

    with pytest.raises(uploads.UploadRejected):
        await uploads.probe(fake, FFPROBE)


async def test_a_real_video_is_accepted_and_described(tmp_path):
    path = _real_video(tmp_path / "real.mp4", seconds=1.0)

    probed = await uploads.probe(path, FFPROBE)

    assert probed.width == 320
    assert probed.height == 240
    assert probed.duration_s == pytest.approx(1.0, abs=0.2)
    assert probed.has_audio


async def test_a_silent_video_is_reported_as_having_no_audio(tmp_path):
    """Not an error here — the route turns it into one, because there is
    no speech to caption."""
    path = _real_video(tmp_path / "silent.mp4", with_audio=False)

    assert not (await uploads.probe(path, FFPROBE)).has_audio


# --------------------------------------------------------------------------
# The HTTP route — what a rejected upload leaves behind
# --------------------------------------------------------------------------


class _FakeQueue:
    def __init__(self):
        self.submitted = []

    async def submit(self, project):
        self.submitted.append(project)


@pytest.fixture
def upload_app(monkeypatch, tmp_path):
    """The route with storage pointed at a temp dir and no database, which
    is the self-hosted shape: no accounts, no billing."""
    from fastapi import FastAPI

    from app.api.routes import uploads as uploads_route
    from app.core import config as core_config
    from app.services import project_store

    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path / "projects")
    monkeypatch.setattr(settings, "ffprobe_binary", FFPROBE)
    project_store.configure(None)

    app = FastAPI()
    app.include_router(uploads_route.router)
    app.state.db_pool = None
    queue = _FakeQueue()
    app.state.render_queue = queue
    return app, queue


def _client(app):
    import httpx

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_a_real_upload_is_stored_and_queued(upload_app, tmp_path):
    app, queue = upload_app
    video = _real_video(tmp_path / "clip.mp4")

    async with _client(app) as client:
        response = await client.post(
            "/api/uploads",
            files={"file": ("holiday.mp4", video.read_bytes(), "video/mp4")},
            data={"language": "en", "title": "My clip"},
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["config"]["source"] == "upload"
    assert body["config"]["topic"] == "My clip"
    # Music would be mixed under footage the user recorded themselves.
    assert body["config"]["music"]["enabled"] is False

    stored = Path(body["source_path"])
    assert stored.is_file()
    assert stored.name.startswith("source"), "the client's filename was used"
    assert "holiday" not in str(stored)
    assert len(queue.submitted) == 1


async def test_a_rejected_upload_leaves_no_project_behind(upload_app):
    """A 422 that still created a row would show up in the user's library
    as a permanently broken project."""
    from app.services import project_store

    app, queue = upload_app

    async with _client(app) as client:
        response = await client.post(
            "/api/uploads",
            files={"file": ("notavideo.mp4", b"PK\x03\x04" + b"\x00" * 512, "video/mp4")},
        )

    assert response.status_code == 422
    assert queue.submitted == []
    assert await project_store.list_projects(None) == []


async def test_a_silent_video_is_refused_with_a_reason(upload_app, tmp_path):
    app, queue = upload_app
    video = _real_video(tmp_path / "silent.mp4", with_audio=False)

    async with _client(app) as client:
        response = await client.post(
            "/api/uploads", files={"file": ("silent.mp4", video.read_bytes(), "video/mp4")}
        )

    assert response.status_code == 422
    assert "no audio" in response.json()["detail"].lower()
    assert queue.submitted == []
