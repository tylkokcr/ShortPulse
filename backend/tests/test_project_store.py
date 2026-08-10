"""Project store tests.

Both backends are exercised through the same cases, so the in-memory one
used by self-hosted installs and the Postgres one used by the hosted
product cannot drift apart in behaviour.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.schemas.project import (
    ProjectConfig,
    ProjectStatus,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptOutput,
    VideoLength,
    VisualMode,
)
from app.services import db
from app.services.project_store import InMemoryProjectStore, PostgresProjectStore

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)


@pytest.fixture(scope="module")
async def pool():
    try:
        p = await asyncpg.create_pool(TEST_DSN, min_size=1, max_size=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres at {TEST_DSN}: {exc}")
    await db.apply_migrations(p)
    yield p
    await p.close()


@pytest.fixture(params=["memory", "postgres"])
async def store(request, pool):
    if request.param == "memory":
        yield InMemoryProjectStore()
    else:
        yield PostgresProjectStore(pool)


def _config(**kwargs) -> ProjectConfig:
    return ProjectConfig(topic="why the sky is blue", **kwargs)


def _script() -> ScriptOutput:
    return ScriptOutput(
        topic="t",
        hook="a hook",
        total_duration_s=8.0,
        scenes=[
            Scene(
                index=0,
                duration_s=4,
                visual=SceneVisual(prompt="a prompt"),
                audio=SceneAudio(voiceover_line="a line"),
            )
        ],
    )


async def test_create_then_read_back(store):
    config = _config()
    created = await store.create_project(config)
    assert created.status == ProjectStatus.DRAFT

    fetched = await store.get_project(config.id)
    assert fetched is not None
    assert fetched.config.id == config.id
    assert fetched.config.topic == config.topic


async def test_unknown_project_is_none(store):
    assert await store.get_project(str(uuid.uuid4())) is None


async def test_config_survives_the_round_trip(store):
    """Non-default settings must come back intact — a lossy round trip
    would silently re-render projects with different settings."""
    config = _config(
        visual_mode=VisualMode.STOCK_MEDIA,
        video_length=VideoLength.LONG,
        language="tr",
    )
    await store.create_project(config)

    fetched = await store.get_project(config.id)
    assert fetched.config.visual_mode == VisualMode.STOCK_MEDIA
    assert fetched.config.video_length == VideoLength.LONG
    assert fetched.config.language == "tr"


async def test_status_and_output_updates_persist(store):
    config = _config()
    await store.create_project(config)

    await store.update_project(config.id, status=ProjectStatus.RENDERING)
    assert (await store.get_project(config.id)).status == ProjectStatus.RENDERING

    await store.update_project(
        config.id, status=ProjectStatus.COMPLETE, output_path="/tmp/final.mp4"
    )
    fetched = await store.get_project(config.id)
    assert fetched.status == ProjectStatus.COMPLETE
    assert fetched.output_path == "/tmp/final.mp4"


async def test_script_round_trips(store):
    """The script is the expensive part of a render; losing it on read
    would mean re-running the LLM to show a finished project."""
    config = _config()
    await store.create_project(config)
    await store.update_project(config.id, script=_script())

    fetched = await store.get_project(config.id)
    assert fetched.script is not None
    assert fetched.script.hook == "a hook"
    assert len(fetched.script.scenes) == 1
    assert fetched.script.scenes[0].audio.voiceover_line == "a line"


async def test_failure_is_recorded(store):
    config = _config()
    await store.create_project(config)
    await store.update_project(config.id, status=ProjectStatus.FAILED, error="boom")

    fetched = await store.get_project(config.id)
    assert fetched.status == ProjectStatus.FAILED
    assert fetched.error == "boom"


async def test_delete_removes_it(store):
    config = _config()
    await store.create_project(config)
    await store.delete_project(config.id)
    assert await store.get_project(config.id) is None


async def test_listing_includes_created_projects(store):
    ids = []
    for _ in range(3):
        config = _config()
        await store.create_project(config)
        ids.append(config.id)

    listed = {p.config.id for p in await store.list_projects()}
    assert set(ids) <= listed


# --- the reason this migration exists -----------------------------------


async def test_postgres_projects_survive_a_restart(pool):
    """A fresh store instance against the same database must still see the
    project. This is the whole point of moving off the in-memory dict,
    which dropped every project (and orphaned every in-flight render)
    whenever the process restarted.
    """
    config = _config(language="tr")
    first = PostgresProjectStore(pool)
    await first.create_project(config)
    await first.update_project(config.id, status=ProjectStatus.COMPLETE, output_path="/tmp/x.mp4")

    # Stands in for a process restart: new store object, same database.
    reborn = PostgresProjectStore(pool)
    fetched = await reborn.get_project(config.id)

    assert fetched is not None
    assert fetched.status == ProjectStatus.COMPLETE
    assert fetched.output_path == "/tmp/x.mp4"
    assert fetched.config.language == "tr"


async def test_in_memory_projects_do_not_survive_a_restart():
    """Documents the limitation the Postgres backend exists to remove."""
    config = _config()
    first = InMemoryProjectStore()
    await first.create_project(config)

    reborn = InMemoryProjectStore()
    assert await reborn.get_project(config.id) is None


async def test_update_rejects_fields_it_cannot_persist(pool):
    """Guards against silently dropping a field: anything not backed by a
    column should fail loudly rather than appear to save."""
    config = _config()
    store = PostgresProjectStore(pool)
    await store.create_project(config)

    with pytest.raises(ValueError, match="unknown project fields"):
        await store.update_project(config.id, not_a_column="x")


async def test_column_names_cannot_be_injected(pool):
    """update_project is the only query assembled with an f-string, so the
    whitelist is what stands between a caller-supplied key and the SQL. A
    field name that isn't a real column must be refused before it reaches
    the database, not quoted and hoped for."""
    config = _config()
    store = PostgresProjectStore(pool)
    await store.create_project(config)

    attacks = {
        "status = 'complete', error = (select 'pwned')": "x",
        "output_path); drop table projects; --": "x",
        "user_id": "00000000-0000-0000-0000-000000000000",  # real column, still not ours to set
    }
    for field, value in attacks.items():
        with pytest.raises(ValueError, match="unknown project fields"):
            await store.update_project(config.id, **{field: value})

    # And the table is still there with the project intact.
    assert (await store.get_project(config.id)) is not None
