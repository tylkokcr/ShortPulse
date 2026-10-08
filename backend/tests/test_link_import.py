"""Bringing a video in from a link: what a link is, what this server will
fetch, and what a video from YouTube may and may not be used for."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from app.services import link_import
from app.services.uploads import UploadRejected
from tests.test_media import media_app  # noqa: F401 - fixture
from tests.test_uploads import _client, _real_video


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ&t=30s",
        "https://youtu.be/aqz-KE-bpKQ?si=abc",
        "https://m.youtube.com/watch?v=aqz-KE-bpKQ",
        "https://www.youtube.com/shorts/aqz-KE-bpKQ",
    ],
)
def test_every_shape_of_youtube_link_is_one_video(url):
    link = link_import.classify(url)
    assert link.kind == "youtube"
    assert link.url == "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def test_share_links_are_rewritten_to_the_file():
    drive = link_import.classify("https://drive.google.com/file/d/1AbC_dEf-123/view?usp=sharing")
    assert drive.kind == "direct" and "id=1AbC_dEf-123" in drive.url and "export=download" in drive.url
    dropbox = link_import.classify("https://www.dropbox.com/s/xyz/match.mp4?dl=0")
    assert dropbox.url.endswith("dl=1") and "dl=0" not in dropbox.url


def test_onedrive_and_box_share_links_are_rewritten_to_the_file():
    import base64

    personal = "https://1drv.ms/v/s!AkxYz123abc"
    link = link_import.classify(personal)
    token = base64.urlsafe_b64encode(personal.encode()).decode().rstrip("=")
    assert link.url == f"https://api.onedrive.com/v1.0/shares/u!{token}/root/content"
    work = link_import.classify(
        "https://contoso-my.sharepoint.com/:v:/g/personal/ann_contoso_com/EaBcD?e=xyz"
    )
    assert "download=1" in work.url and "e=xyz" in work.url
    box = link_import.classify("https://app.box.com/s/abc123def456")
    assert box.url == "https://app.box.com/shared/static/abc123def456"
    company = link_import.classify("https://acme.app.box.com/s/zz99")
    assert company.url == "https://acme.app.box.com/shared/static/zz99"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://host/x.mp4", "not a link", ""])
def test_anything_but_a_web_link_is_refused(url):
    with pytest.raises(UploadRejected):
        link_import.classify(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/video.mp4",
        "http://localhost:8000/api/projects",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/x.mp4",
        "http://[::1]/x.mp4",
    ],
)
async def test_this_server_never_fetches_its_own_network(url, tmp_path):
    with pytest.raises(UploadRejected):
        await link_import.fetch_direct(url, tmp_path / "out.mp4", 10_000_000)
    assert not (tmp_path / "out.mp4").exists()


async def _import(client, url: str, rights: bool = True):
    return await client.post("/api/media/import", json={"url": url, "rights_confirmed": rights})


async def _wait(client, import_id: str) -> dict:
    for _ in range(100):
        body = (await client.get(f"/api/media/import/{import_id}")).json()
        if body["status"] != "running":
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("import never finished")


async def test_a_link_needs_the_rights_confirmed(media_app):  # noqa: F811
    app, _ = media_app
    async with _client(app) as client:
        response = await _import(client, "https://example.com/v.mp4", rights=False)
    assert response.status_code == 422


async def test_youtube_is_refused_unless_the_operator_turned_it_on(media_app, monkeypatch):  # noqa: F811
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "youtube_import_enabled", False)
    app, _ = media_app
    async with _client(app) as client:
        response = await _import(client, "https://youtu.be/aqz-KE-bpKQ")
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "youtube_disabled"


async def test_a_linked_file_lands_in_my_files(media_app, monkeypatch, tmp_path):  # noqa: F811
    video = _real_video(tmp_path / "remote.mp4", seconds=1.0)

    async def fake_fetch(url, destination, cap):
        shutil.copy2(video, destination)
        return destination.stat().st_size

    monkeypatch.setattr(link_import, "fetch_direct", fake_fetch)
    app, _ = media_app
    async with _client(app) as client:
        started = await _import(client, "https://example.com/match.mp4")
        assert started.status_code == 202, started.text
        done = await _wait(client, started.json()["id"])
        listing = (await client.get("/api/media")).json()
    assert done["status"] == "done", done
    assert done["media"]["origin"] == "link" and done["media"]["expires_at"] is None
    assert [f["id"] for f in listing["files"]] == [done["media"]["id"]]


async def test_a_link_that_is_not_a_video_fails_and_leaves_nothing(media_app, monkeypatch, tmp_path):  # noqa: F811
    async def fake_fetch(url, destination, cap):
        destination.write_text("<html>sign in</html>")
        return 20

    monkeypatch.setattr(link_import, "fetch_direct", fake_fetch)
    app, _ = media_app
    async with _client(app) as client:
        done = await _wait(client, (await _import(client, "https://example.com/x")).json()["id"])
        listing = (await client.get("/api/media")).json()
    assert done["status"] == "failed" and done["error"]
    assert listing["files"] == []
    assert not any((tmp_path / "media").glob("*.mp4"))


async def test_a_youtube_video_expires_and_its_projects_are_never_posted(
    media_app, monkeypatch, tmp_path  # noqa: F811
):
    from datetime import UTC, datetime, timedelta

    from app.core.config import get_settings
    from app.services import media_store

    monkeypatch.setattr(get_settings(), "youtube_import_enabled", True)
    video = _real_video(tmp_path / "yt.mp4", seconds=1.0)

    def fake_youtube(url, destination, cap, max_s, ffmpeg):
        shutil.copy2(video, destination)
        return "Someone's upload"

    monkeypatch.setattr(link_import, "fetch_youtube", fake_youtube)
    app, queue = media_app
    async with _client(app) as client:
        done = await _wait(client, (await _import(client, "https://youtu.be/aqz-KE-bpKQ")).json()["id"])
        assert done["status"] == "done", done
        media = done["media"]
        assert media["origin"] == "youtube" and media["name"] == "Someone's upload"
        expires = datetime.fromisoformat(media["expires_at"])
        assert timedelta(hours=23) < expires - datetime.now(UTC) <= timedelta(days=1)

        made = await client.post("/api/uploads", data={"media_id": media["id"]})
        assert made.status_code == 201, made.text
        assert queue.submitted[0].config.source_origin == "youtube"

        # A day later it is gone from My files and from disk.
        kept = await media_store.get_owned(media["id"], None)
        assert kept is not None
        kept.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        listing = (await client.get("/api/media")).json()
    assert listing["files"] == []
    assert not Path(kept.path).exists()
    # The project made from it keeps its own copy.
    assert Path(queue.submitted[0].source_path).is_file()


async def test_publishing_a_youtube_import_is_refused(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api.routes import social
    from app.schemas.project import ProjectConfig
    from app.services import project_store

    project = SimpleNamespace(
        output_path="/tmp/final.mp4", config=ProjectConfig(topic="x", source_origin="youtube")
    )

    async def owner_of(_):
        return "u1"

    async def get_project(_):
        return project

    class Queue:
        enabled = True

    monkeypatch.setattr(project_store, "owner_of", owner_of)
    monkeypatch.setattr(project_store, "get_project", get_project)
    monkeypatch.setattr(social, "_require_pool", lambda request: object())
    monkeypatch.setattr(social, "_queue", lambda request: Queue())
    body = social.PublishRequest(project_id="p1", connection_id="c1", title="t")
    with pytest.raises(HTTPException) as refused:
        await social.publish_now(body, request=None, user_id="u1")
    assert refused.value.status_code == 409
    assert refused.value.detail["error"] == "imported_from_youtube"
