"""What the pipeline saves, and when.

run_pipeline mutates the script in place as it goes: the audio stage fills
in file paths and word timings, the visual stage fills in asset paths and
stock-footage attribution. Only the stages that call update_project persist
any of it, so the choreography is easy to get wrong in a way nothing else
notices — the video renders correctly either way, and only the stored
project comes back hollow.

That is exactly how the attribution bug shipped: the script was saved right
after generation and never again.

The engines are stubbed because none of them are what's under test here.
"""

from __future__ import annotations

import os

import asyncpg
import pytest

from app.core.config import get_settings
from app.schemas.project import (
    ProjectConfig,
    ProjectStatus,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptOutput,
    StockAttribution,
    VisualMode,
    Word,
)
from app.services import db, project_store, render_manager

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)


@pytest.fixture(scope="module")
async def pool():
    try:
        p = await db.connect(TEST_DSN, min_size=1, max_size=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres at {TEST_DSN}: {exc}")
    await db.apply_migrations(p)
    yield p
    await db.disconnect()


@pytest.fixture(autouse=True)
def _postgres_backend(pool):
    project_store.configure(pool)
    yield
    project_store.configure(None)


def _script() -> ScriptOutput:
    return ScriptOutput(
        topic="bees",
        hook="Bees navigate by the sun.",
        total_duration_s=8.0,
        scenes=[
            Scene(
                index=i,
                duration_s=4,
                visual=SceneVisual(prompt=f"scene {i}"),
                audio=SceneAudio(voiceover_line=f"line {i}"),
            )
            for i in range(2)
        ],
    )


@pytest.fixture
def stubbed_pipeline(monkeypatch, tmp_path):
    """Replaces every engine with something instant that mutates the scenes
    the way the real ones do."""

    async def fake_generate_script(**kwargs):
        return _script()

    async def fake_audio(scene, *args, **kwargs):
        scene.audio.audio_path = str(tmp_path / f"scene_{scene.index}.wav")
        scene.audio.duration_ms = 4000
        scene.audio.words = [Word(text="line", start_ms=0, end_ms=500)]

    async def fake_visual(scene, mode, out_dir, settings):
        scene.visual.asset_path = str(tmp_path / f"scene_{scene.index}.mp4")
        scene.visual.attribution = StockAttribution(
            provider="Pexels",
            provider_url="https://www.pexels.com",
            author=f"Photographer {scene.index}",
            author_url="https://www.pexels.com/@someone",
            source_url="https://www.pexels.com/video/x-1/",
        )

    async def fake_render(*args, **kwargs):
        output = tmp_path / "final.mp4"
        output.write_bytes(b"fake mp4")
        return output

    monkeypatch.setattr(render_manager.script_engine, "generate_script", fake_generate_script)
    monkeypatch.setattr(render_manager.audio_engine, "process_scene_audio", fake_audio)
    monkeypatch.setattr(render_manager.visual_engine, "generate_scene_visual", fake_visual)
    monkeypatch.setattr(render_manager.render_engine, "render_project", fake_render)


async def _run(config: ProjectConfig):
    project = await project_store.create_project(config)
    await render_manager.run_pipeline(project, get_settings())
    return await project_store.get_project(config.id)


@pytest.fixture
def config() -> ProjectConfig:
    return ProjectConfig(topic="how bees navigate", visual_mode=VisualMode.STOCK_MEDIA)


async def test_stock_attribution_survives_the_render(config, stubbed_pipeline):
    """The bug this file exists for. Pexels requires the credit to be
    displayed, and the UI can only display what was stored."""
    stored = await _run(config)

    assert stored.status == ProjectStatus.COMPLETE
    credits = [scene.visual.attribution for scene in stored.script.scenes]
    assert all(c is not None for c in credits), "attribution lost on the way to the database"
    assert credits[0].author == "Photographer 0"
    assert credits[0].source_url == "https://www.pexels.com/video/x-1/"


async def test_word_timings_survive_the_render(config, stubbed_pipeline):
    """Transcription is one of the slowest stages; losing its output means
    the synced transcript panel has nothing to work with."""
    stored = await _run(config)

    words = stored.script.scenes[0].audio.words
    assert words, "word timings lost on the way to the database"
    assert words[0].text == "line"


async def test_asset_paths_survive_the_render(config, stubbed_pipeline):
    stored = await _run(config)

    scene = stored.script.scenes[0]
    assert scene.audio.audio_path
    assert scene.visual.asset_path
    assert scene.audio.duration_ms == 4000


async def test_the_scene_breakdown_appears_before_the_slow_stages(config, monkeypatch, tmp_path):
    """The early save is worth keeping: it's what lets the UI show scenes
    while audio and visuals grind away. Assert it still happens, so the fix
    for the late save doesn't quietly remove it."""
    saved_scripts = []
    real_update = project_store.update_project

    async def spy(project_id, **updates):
        if "script" in updates:
            saved_scripts.append(updates["script"])
        return await real_update(project_id, **updates)

    monkeypatch.setattr(project_store, "update_project", spy)

    async def fake_generate_script(**kwargs):
        return _script()

    async def slow_audio(scene, *args, **kwargs):
        assert saved_scripts, "audio started before the scene breakdown was saved"
        scene.audio.audio_path = "x"
        scene.audio.duration_ms = 4000

    async def fake_visual(scene, mode, out_dir, settings):
        scene.visual.asset_path = "y"

    async def fake_render(*args, **kwargs):
        output = tmp_path / "final.mp4"
        output.write_bytes(b"x")
        return output

    monkeypatch.setattr(render_manager.script_engine, "generate_script", fake_generate_script)
    monkeypatch.setattr(render_manager.audio_engine, "process_scene_audio", slow_audio)
    monkeypatch.setattr(render_manager.visual_engine, "generate_scene_visual", fake_visual)
    monkeypatch.setattr(render_manager.render_engine, "render_project", fake_render)

    await _run(config)

    assert len(saved_scripts) == 2, "expected an early snapshot and a final save"
