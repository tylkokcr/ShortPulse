"""Continuing a series: only a finished outbreak episode can be continued,
and the next one is that series' next, in its language."""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.api.routes import projects as projects_route
from app.core import config as core_config
from app.schemas.project import (
    ProjectConfig,
    ProjectStatus,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptFormat,
    ScriptOutput,
)
from app.services import project_store


class _Queue:
    def __init__(self):
        self.submitted = []

    async def submit(self, project):
        self.submitted.append(project)


@pytest.fixture
def api(monkeypatch):
    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "replicate_api_token", "r8_test")
    project_store.configure(None)
    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = None
    queue = _Queue()
    app.state.render_queue = queue
    return app, queue


async def _episode(script_format=ScriptFormat.OUTBREAK, status=ProjectStatus.COMPLETE):
    project = await project_store.create_project(
        ProjectConfig(topic="Zombies in Istanbul", language="tr", script_format=script_format)
    )
    script = ScriptOutput(
        topic="x", hook="h", total_duration_s=3,
        scenes=[Scene(index=0, duration_s=3, visual=SceneVisual(prompt="p"),
                      audio=SceneAudio(voiceover_line="l"))],
    )
    await project_store.update_project(project.config.id, status=status, script=script)
    return project.config.id


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_the_next_episode_is_the_series_next_in_its_language(api):
    app, queue = api
    previous = await _episode()
    async with _client(app) as client:
        response = await client.post(
            "/api/projects",
            json={"topic": "next", "language": "en", "continues_from": previous},
        )
    assert response.status_code == 201
    config = queue.submitted[0].config
    assert config.continues_from == previous
    assert config.script_format == ScriptFormat.OUTBREAK and config.language == "tr"


@pytest.mark.parametrize(
    "kind",
    [
        {"script_format": ScriptFormat.WHAT_IF},
        {"status": ProjectStatus.RENDERING},
    ],
)
async def test_only_a_finished_outbreak_episode_can_be_continued(api, kind):
    app, queue = api
    previous = await _episode(**kind)
    async with _client(app) as client:
        response = await client.post(
            "/api/projects", json={"topic": "next", "continues_from": previous}
        )
    assert response.status_code == 422 and not queue.submitted


async def test_an_unknown_episode_is_not_found(api):
    app, _ = api
    async with _client(app) as client:
        response = await client.post(
            "/api/projects", json={"topic": "next", "continues_from": str(uuid.uuid4())}
        )
    assert response.status_code == 404


async def test_the_next_episode_draws_its_cast_from_the_last_ones_sheets(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.schemas.project import CastMember
    from app.services import render_manager

    monkeypatch.setattr(render_manager, "project_dir", lambda pid: tmp_path / pid)
    earlier = render_manager.cast_sheet_path(tmp_path / "ep1", "Zehra")
    earlier.parent.mkdir(parents=True)
    earlier.write_bytes(b"\x89PNG zehra")

    scene = Scene(index=0, duration_s=3, visual=SceneVisual(prompt="p"),
                  audio=SceneAudio(voiceover_line="l"), cast=["Zehra"])
    script = ScriptOutput(
        topic="x", hook="h", total_duration_s=3, scenes=[scene],
        cast=[CastMember(name="Zehra", gender="woman", age=34, look="auburn hair")],
    )
    previous = SimpleNamespace(config=SimpleNamespace(id="ep1"))
    settings = SimpleNamespace(visual_provider="local", replicate_api_token=None)

    sheets = await render_manager._cast_sheets(
        script, tmp_path / "ep2", previous, SimpleNamespace(art_style="vector"), settings
    )

    assert sheets["Zehra"].read_bytes() == b"\x89PNG zehra"
    assert "34-year-old woman, auburn hair" in sheets["Zehra"].with_suffix(".txt").read_text()


async def test_a_story_stops_rather_than_draw_its_cast_from_words(tmp_path, monkeypatch):
    """A rate-limited episode came out with a new stranger every shot: when
    a cast member's sheet cannot be drawn after retries, the render fails
    (and is refunded) instead."""
    from types import SimpleNamespace

    import pytest as _pytest

    from app.engines import visual_engine
    from app.schemas.project import CastMember
    from app.services import render_manager

    calls = {"n": 0}

    async def busy(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("429")

    async def no_wait(_s):
        return None

    monkeypatch.setattr(visual_engine, "generate_character_sheet", busy)
    monkeypatch.setattr(visual_engine, "image_backend", lambda s: visual_engine.ImageBackend.REPLICATE)
    monkeypatch.setattr(render_manager.asyncio, "sleep", no_wait)
    scene = Scene(index=0, duration_s=3, visual=SceneVisual(prompt="p"),
                  audio=SceneAudio(voiceover_line="l"), cast=["Elif"])
    script = ScriptOutput(topic="x", hook="h", total_duration_s=3, scenes=[scene],
                          cast=[CastMember(name="Elif", gender="woman", age=32, look="x")])

    with _pytest.raises(RuntimeError, match="Elif"):
        await render_manager._cast_sheets(
            script, tmp_path, None, SimpleNamespace(art_style="vector"), SimpleNamespace()
        )
    assert calls["n"] == 3
