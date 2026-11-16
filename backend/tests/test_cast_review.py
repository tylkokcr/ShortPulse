"""The cast review: a story's first episode stops once its people are drawn,
for the owner to change a voice or a face before the episode is made."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.routes import projects as projects_route
from app.core import config as core_config
from app.schemas.project import (
    CastMember,
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
    app.state.render_queue = _Queue()
    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _script() -> ScriptOutput:
    return ScriptOutput(
        topic="x", hook="h", total_duration_s=3,
        scenes=[Scene(index=0, duration_s=3, visual=SceneVisual(prompt="p"),
                      audio=SceneAudio(voiceover_line="l"), cast=["Elif"], speaker="Elif")],
        cast=[CastMember(name="Elif", gender="woman", age=32, look="black bob",
                         voice_id="elevenlabs:a")],
    )


async def _in_review(**config) -> str:
    project = await project_store.create_project(
        ProjectConfig(topic="t", language="tr", script_format=ScriptFormat.STORY,
                      review_cast=True, **config)
    )
    await project_store.update_project(project.config.id, status=ProjectStatus.REVIEW, script=_script())
    return project.config.id


async def test_only_a_storys_first_episode_is_reviewed_and_never_pre_approved(api):
    async with _client(api) as client:
        story = await client.post("/api/projects", json={
            "topic": "t", "script_format": "story", "review_cast": True, "cast_approved": True,
            "cast_redraws": -9,
        })
        other = await client.post("/api/projects", json={"topic": "t", "review_cast": True})
    config = story.json()["config"]
    assert config["review_cast"] is True and config["cast_approved"] is False
    assert config["cast_redraws"] == 0
    assert other.json()["config"]["review_cast"] is False


async def test_the_pipeline_stops_once_the_cast_is_drawn(tmp_path, monkeypatch):
    from app.services import render_manager

    drawn = []

    async def write_script(*args):
        return _script()

    async def sheets(script, *args):
        drawn.append([m.name for m in script.cast])
        return {}

    async def no_voices(*args, **kwargs):
        raise AssertionError("voiced before the review")

    async def quiet(*args, **kwargs):
        return None

    project_store.configure(None)
    monkeypatch.setattr(render_manager, "project_dir", lambda pid: tmp_path / pid)
    monkeypatch.setattr(render_manager, "_write_script", write_script)
    monkeypatch.setattr(render_manager, "_cast_sheets", sheets)
    monkeypatch.setattr(render_manager.audio_engine, "process_scene_audio", no_voices)
    monkeypatch.setattr(render_manager, "_emit", quiet)
    project = await project_store.create_project(
        ProjectConfig(topic="t", script_format=ScriptFormat.STORY, review_cast=True)
    )

    await render_manager.run_pipeline(project, core_config.get_settings())

    stored = await project_store.get_project(project.config.id)
    assert stored is not None and stored.status == ProjectStatus.REVIEW
    assert drawn == [["Elif"]] and stored.script is not None


async def test_an_approved_cast_is_rendered_from_the_reviewed_script(tmp_path, monkeypatch):
    from app.services import render_manager

    async def no_script(*args):
        raise AssertionError("script written again")

    voiced = []

    async def voices(scene, voice, *args, **kwargs):
        voiced.append(voice.voice_id)
        raise RuntimeError("stop here")

    async def quiet(*args, **kwargs):
        return None

    project_store.configure(None)
    monkeypatch.setattr(render_manager, "project_dir", lambda pid: tmp_path / pid)
    monkeypatch.setattr(render_manager, "_write_script", no_script)
    monkeypatch.setattr(render_manager.audio_engine, "process_scene_audio", voices)
    monkeypatch.setattr(render_manager, "_emit", quiet)
    monkeypatch.setattr(render_manager, "_refund_failed_render", quiet)
    pid = await _in_review(cast_approved=True)
    project = await project_store.get_project(pid)
    assert project is not None

    await render_manager.run_pipeline(project, core_config.get_settings())

    assert voiced == ["elevenlabs:a"]


async def test_approving_queues_the_episode_and_only_from_review(api):
    pid = await _in_review()
    async with _client(api) as client:
        ok = await client.post(f"/api/projects/{pid}/cast/approve")
        again = await client.post(f"/api/projects/{pid}/cast/approve")
    assert ok.status_code == 200
    assert ok.json()["status"] == "draft" and ok.json()["config"]["cast_approved"] is True
    assert len(api.state.render_queue.submitted) == 1
    assert again.status_code == 409


async def test_a_voice_must_be_one_of_the_accounts(api, monkeypatch):
    from app.services import elevenlabs_voices

    async def choices(language):
        return [{"voice_id": "elevenlabs:b", "name": "b", "kind": "woman", "preview_url": None}]

    monkeypatch.setattr(elevenlabs_voices, "voice_choices", choices)
    pid = await _in_review()
    async with _client(api) as client:
        bad = await client.post(f"/api/projects/{pid}/cast/Elif", json={"voice_id": "minimax:x"})
        good = await client.post(f"/api/projects/{pid}/cast/Elif", json={"voice_id": "elevenlabs:b"})
    assert bad.status_code == 422
    assert good.json()["script"]["cast"][0]["voice_id"] == "elevenlabs:b"


async def test_a_new_look_redraws_up_to_the_limit(api, monkeypatch):
    from app.services import render_manager

    redrawn = []

    async def redraw(project, name, settings):
        redrawn.append((name, next(m.look for m in project.script.cast if m.name == name)))

    monkeypatch.setattr(render_manager, "redraw_cast_member", redraw)
    pid = await _in_review()
    async with _client(api) as client:
        ok = await client.post(f"/api/projects/{pid}/cast/Elif", json={"look": "long red hair"})
        limit = projects_route.MAX_CAST_REDRAWS
        project = await project_store.get_project(pid)
        assert project is not None
        await project_store.update_project(
            pid, config=project.config.model_copy(update={"cast_redraws": limit})
        )
        over = await client.post(f"/api/projects/{pid}/cast/Elif", json={"look": "short grey hair"})
    assert redrawn == [("Elif", "long red hair")]
    assert ok.json()["config"]["cast_redraws"] == 1
    assert ok.json()["script"]["cast"][0]["look"] == "long red hair"
    assert over.status_code == 429
