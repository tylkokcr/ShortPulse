"""My files: keeping a file once and using it again."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.test_uploads import FFPROBE, _client, _FakeQueue, _real_video

pytestmark = pytest.mark.skipif(
    shutil.which(FFPROBE) is None and not Path(FFPROBE).exists(),
    reason=f"{FFPROBE} not available",
)


@pytest.fixture
def media_app(monkeypatch, tmp_path):
    from fastapi import FastAPI

    from app.api.routes import beat_edits, media, uploads
    from app.core import config as core_config
    from app.services import media_store, project_store
    from app.services.media_tokens import MediaTokenSigner

    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path / "projects")
    monkeypatch.setattr(settings, "media_root", tmp_path / "media")
    monkeypatch.setattr(settings, "ffprobe_binary", FFPROBE)
    project_store.configure(None)
    media_store.configure(None)

    app = FastAPI()
    for module in (media, uploads, beat_edits):
        app.include_router(module.router)
    app.state.db_pool = None
    app.state.media_signer = MediaTokenSigner("test-secret")
    queue = _FakeQueue()
    app.state.render_queue = queue
    return app, queue


async def _keep_video(client, tmp_path, name="clip.mp4"):
    video = _real_video(tmp_path / name, seconds=1.0)
    response = await client.post(
        "/api/media", files={"file": (name, video.read_bytes(), "video/mp4")}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_kept_video_is_listed_with_what_a_probe_says(media_app, tmp_path):
    app, _ = media_app
    async with _client(app) as client:
        kept = await _keep_video(client, tmp_path)
        listing = (await client.get("/api/media")).json()
    assert kept["kind"] == "video" and kept["width"] == 320 and kept["duration_s"] > 0.5
    assert [f["id"] for f in listing["files"]] == [kept["id"]]
    assert listing["used_bytes"] == kept["size_bytes"]
    assert (tmp_path / "media" / f"{kept['id']}.jpg").is_file()


async def test_a_file_that_is_neither_video_nor_audio_is_refused(media_app):
    app, _ = media_app
    async with _client(app) as client:
        response = await client.post("/api/media", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert response.status_code == 422


async def test_a_kept_video_can_be_captioned_without_uploading_it_again(media_app, tmp_path):
    app, queue = media_app
    async with _client(app) as client:
        kept = await _keep_video(client, tmp_path)
        response = await client.post("/api/uploads", data={"media_id": kept["id"]})
    assert response.status_code == 201, response.text
    assert len(queue.submitted) == 1
    source = Path(queue.submitted[0].source_path)
    assert source.is_file() and source.stat().st_size == kept["size_bytes"]


async def test_deleting_the_file_leaves_the_project_its_copy(media_app, tmp_path):
    app, queue = media_app
    async with _client(app) as client:
        kept = await _keep_video(client, tmp_path)
        await client.post("/api/uploads", data={"media_id": kept["id"]})
        assert (await client.delete(f"/api/media/{kept['id']}")).status_code == 204
    assert Path(queue.submitted[0].source_path).is_file()
    assert not (tmp_path / "media" / f"{kept['id']}.mp4").exists()


async def test_an_upload_can_be_kept_as_well(media_app, tmp_path):
    app, _ = media_app
    video = _real_video(tmp_path / "in.mp4", seconds=1.0)
    async with _client(app) as client:
        response = await client.post(
            "/api/uploads",
            files={"file": ("trip.mp4", video.read_bytes(), "video/mp4")},
            data={"save_to_files": "true"},
        )
        assert response.status_code == 201
        listing = (await client.get("/api/media")).json()
    assert [f["name"] for f in listing["files"]] == ["trip.mp4"]


async def test_someone_elses_id_is_not_usable(media_app, tmp_path, monkeypatch):
    app, _ = media_app
    from app.services import media_store

    async with _client(app) as client:
        kept = await _keep_video(client, tmp_path)
        stored = await media_store._store.get(kept["id"])
        stored.user_id = "someone-else"
        response = await client.post("/api/uploads", data={"media_id": kept["id"]})
        url = await client.get(f"/api/media/{kept['id']}/url")
    assert response.status_code == 422
    assert url.status_code == 404


async def test_a_signed_url_streams_and_a_project_token_does_not(media_app, tmp_path):
    app, _ = media_app
    async with _client(app) as client:
        kept = await _keep_video(client, tmp_path)
        urls = (await client.get(f"/api/media/{kept['id']}/url")).json()
        ok = await client.get(urls["url"])
        # A token minted for a project id must not open a file.
        token, _ = app.state.media_signer.sign(kept["id"])
        forged = await client.get(f"/api/media/{kept['id']}/stream?token={token}")
    assert ok.status_code == 200 and ok.headers["content-type"] == "video/mp4"
    assert forged.status_code == 403


async def test_the_quota_refuses_what_does_not_fit(media_app, tmp_path, monkeypatch):
    app, _ = media_app
    from app.core import config as core_config

    monkeypatch.setattr(core_config.get_settings(), "media_quota_mb", 0)
    video = _real_video(tmp_path / "big.mp4", seconds=1.0)
    async with _client(app) as client:
        response = await client.post(
            "/api/media", files={"file": ("big.mp4", video.read_bytes(), "video/mp4")}
        )
    assert response.status_code == 422


async def test_a_beat_edit_takes_clips_from_my_files(media_app, tmp_path):
    app, queue = media_app
    from app.api.routes.music import available_tracks

    async with _client(app) as client:
        first = await _keep_video(client, tmp_path, "a.mp4")
        second = await _keep_video(client, tmp_path, "b.mp4")
        response = await client.post(
            "/api/beat-edits",
            data={
                "clip_media_ids": [first["id"], second["id"]],
                "music_track_id": available_tracks()[0].id,
            },
        )
    assert response.status_code == 201, response.text
    assert response.json()["config"]["beat_edit"]["clip_count"] == 2


async def test_the_same_upload_kept_twice_is_kept_once(media_app, tmp_path):
    app, _ = media_app
    video = _real_video(tmp_path / "in.mp4", seconds=1.0)
    async with _client(app) as client:
        for _ in range(2):
            response = await client.post(
                "/api/uploads",
                files={"file": ("trip.mp4", video.read_bytes(), "video/mp4")},
                data={"save_to_files": "true"},
            )
            assert response.status_code == 201, response.text
        listing = (await client.get("/api/media")).json()
    assert [f["name"] for f in listing["files"]] == ["trip.mp4"]
