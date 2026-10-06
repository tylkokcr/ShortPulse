"""Short uploads get the accurate Whisper model, long ones the fast one."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.schemas.project import ProjectConfig, ProjectSource
from app.services import render_manager


def _upload(**kwargs) -> ProjectConfig:
    return ProjectConfig(topic="x", source=ProjectSource.UPLOAD, **kwargs)


def _settings(**overrides) -> Settings:
    return Settings(
        whisper_model_size="small",
        whisper_short_model_size="medium",
        whisper_short_max_s=180,
        **overrides,
    )


@pytest.fixture
def source_of(monkeypatch):
    def set_length(seconds: float) -> None:
        async def fake_probe(path, ffprobe):
            return int(seconds * 1000)

        monkeypatch.setattr(render_manager.render_engine, "probe_duration_ms", fake_probe)

    return set_length


async def test_a_short_upload_is_read_by_the_accurate_model(source_of) -> None:
    source_of(33)
    model = await render_manager._whisper_model_for(Path("x.mp4"), _upload(), _settings())
    assert model == "medium"


async def test_a_long_upload_keeps_the_fast_model(source_of) -> None:
    source_of(40 * 60)
    model = await render_manager._whisper_model_for(Path("x.mp4"), _upload(), _settings())
    assert model == "small"


async def test_an_extraction_is_judged_by_its_window_not_its_file(source_of) -> None:
    source_of(60 * 60)
    config = _upload(clip_count=3, clip_from_s=600, clip_to_s=720)
    model = await render_manager._whisper_model_for(Path("x.mp4"), config, _settings())
    assert model == "medium"


async def test_an_unmeasurable_file_is_assumed_long(monkeypatch) -> None:
    async def broken(path, ffprobe):
        raise RuntimeError("no duration")

    monkeypatch.setattr(render_manager.render_engine, "probe_duration_ms", broken)
    model = await render_manager._whisper_model_for(Path("x.mp4"), _upload(), _settings())
    assert model == "small"


async def test_an_empty_setting_turns_it_off(source_of) -> None:
    source_of(10)
    settings = _settings()
    settings.whisper_short_model_size = ""
    assert await render_manager._whisper_model_for(Path("x.mp4"), _upload(), settings) == "small"
