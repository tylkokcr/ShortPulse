"""Asking what came out wrong, and keeping the answer.

This is the only signal of its kind in the product. The privacy page
promises no analytics, no tracking pixels and no third-party scripts, so
there is no vendor dashboard to fall back on — if this table is wrong or
empty, nobody finds out which modes and styles produce bad scenes.

What the tests care about, in order: that a verdict survives the user
deleting the render it was about, that changing your mind replaces rather
than appends, and that one person cannot read another's.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import current_user_id
from app.api.routes import projects as projects_route
from app.schemas.project import (
    ProjectConfig,
    ProjectStatus,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptOutput,
    VisualMode,
)
from app.services import db, feedback, project_store
from app.services.media_tokens import MediaTokenSigner

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


@pytest.fixture
async def user(pool):
    return str(
        await pool.fetchval(
            "insert into app_users (email) values ($1) returning id",
            f"{uuid.uuid4()}@example.test",
        )
    )


async def _project(user_id: str | None, mode=VisualMode.FAST_HYBRID):
    config = ProjectConfig(topic="quiet people", visual_mode=mode, art_style="photoreal")
    await project_store.create_project(config, user_id)
    return await project_store.update_project(
        config.id,
        status=ProjectStatus.COMPLETE,
        script=ScriptOutput(
            topic="t",
            hook="h",
            total_duration_s=8.0,
            scenes=[
                Scene(
                    index=i,
                    duration_s=4.0,
                    visual=SceneVisual(prompt=f"s{i}"),
                    audio=SceneAudio(voiceover_line=f"l{i}"),
                )
                for i in range(2)
            ],
        ),
    )


def _app(pool, user_id: str | None):
    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = pool
    app.state.render_queue = None
    app.state.media_signer = MediaTokenSigner("test-secret", ttl_s=900)
    app.dependency_overrides[current_user_id] = lambda: user_id
    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _send(app, project_id, **body):
    async with _client(app) as client:
        return await client.post(f"/api/projects/{project_id}/feedback", json=body)


# --- recording -----------------------------------------------------------


async def test_a_scene_verdict_is_recorded_with_its_context(pool, user):
    """Mode and style are what make the table answerable. Without them a
    row says "someone disliked something", which is not a finding."""
    project = await _project(user)

    response = await _send(_app(pool, user), project.config.id, scene_index=1,
                           rating="down", reason="visual", note="hands were wrong")

    assert response.status_code == 200
    row = await pool.fetchrow(
        "select * from feedback where project_id = $1", project.config.id
    )
    assert (row["scene_index"], row["rating"], row["reason"]) == (1, "down", "visual")
    assert (row["visual_mode"], row["art_style"]) == ("fast_hybrid", "photoreal")


async def test_the_whole_video_can_be_rated_too(pool, user):
    project = await _project(user)

    await _send(_app(pool, user), project.config.id, rating="up")

    assert await pool.fetchval(
        "select scene_index from feedback where project_id = $1", project.config.id
    ) is None


async def test_changing_your_mind_replaces_the_verdict(pool, user):
    """Thumbing a scene down, re-rolling it and being happy is one opinion
    that changed, not two opinions."""
    project = await _project(user)
    app = _app(pool, user)

    await _send(app, project.config.id, scene_index=0, rating="down", reason="visual")
    await _send(app, project.config.id, scene_index=0, rating="up")

    rows = await pool.fetch(
        "select rating from feedback where project_id = $1 and scene_index = 0",
        project.config.id,
    )
    assert [r["rating"] for r in rows] == ["up"]


async def test_a_scene_and_the_whole_video_are_separate_verdicts(pool, user):
    """The partial indexes exist because `scene_index is null` does not
    compare equal to itself — get that wrong and one overwrites the other."""
    project = await _project(user)
    app = _app(pool, user)

    await _send(app, project.config.id, rating="up")
    await _send(app, project.config.id, scene_index=0, rating="down", reason="pacing")

    assert await pool.fetchval(
        "select count(*) from feedback where project_id = $1", project.config.id
    ) == 2


# --- what it has to survive ---------------------------------------------


async def test_a_verdict_outlives_the_render_it_was_about(pool, user):
    """The case the denormalised columns exist for.

    Deleting a render you disliked is the most likely thing to do with
    one, and losing the complaint at that exact moment would leave the
    table recording only the videos people were happy with.
    """
    project = await _project(user)
    await _send(_app(pool, user), project.config.id, scene_index=0,
                rating="down", reason="visual")

    await project_store.delete_project(project.config.id)

    row = await pool.fetchrow(
        "select project_id, visual_mode, art_style, reason from feedback "
        "where visual_mode = 'fast_hybrid' order by created_at desc limit 1"
    )
    assert row["project_id"] is None       # the reference went
    assert row["reason"] == "visual"       # the finding did not
    assert (row["visual_mode"], row["art_style"]) == ("fast_hybrid", "photoreal")


# --- who can see it ------------------------------------------------------


async def test_the_project_carries_back_only_your_own_verdicts(pool, user):
    """Feedback is a private note to us, not a review other people read."""
    project = await _project(user)
    stranger = str(
        await pool.fetchval(
            "insert into app_users (email) values ($1) returning id",
            f"{uuid.uuid4()}@example.test",
        )
    )
    await _send(_app(pool, user), project.config.id, scene_index=0, rating="down")

    mine = await feedback.for_project(pool, project.config.id, user)
    theirs = await feedback.for_project(pool, project.config.id, stranger)

    assert [f.scene_index for f in mine] == [0]
    assert theirs == []


async def test_the_get_response_shows_it_back(pool, user):
    """So a scene already flagged is not asked about twice."""
    project = await _project(user)
    app = _app(pool, user)
    await _send(app, project.config.id, scene_index=1, rating="down", reason="match")

    async with _client(app) as client:
        body = (await client.get(f"/api/projects/{project.config.id}")).json()

    assert [(f["scene_index"], f["reason"]) for f in body["feedback"]] == [(1, "match")]


# --- refusing nonsense ---------------------------------------------------


async def test_an_unknown_reason_is_refused(pool, user):
    """The fixed list is what keeps "how often is it the visual" a query
    rather than a reading exercise."""
    project = await _project(user)

    response = await _send(_app(pool, user), project.config.id, scene_index=0,
                           rating="down", reason="vibes")

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unknown_reason"


async def test_a_scene_that_does_not_exist_is_refused(pool, user):
    project = await _project(user)

    response = await _send(_app(pool, user), project.config.id, scene_index=99, rating="down")

    assert response.status_code == 422


async def test_a_rating_that_is_not_up_or_down_is_refused(pool, user):
    project = await _project(user)

    response = await _send(_app(pool, user), project.config.id, rating="excellent")

    assert response.status_code == 422


async def test_self_hosting_records_nothing_and_does_not_fail(pool):
    """No user to attribute it to and no product team to tell. Silently
    fine rather than an error in the UI of an install that has no us."""
    project = await _project(None)

    response = await _send(_app(pool, None), project.config.id, rating="up")

    assert response.status_code == 200
    assert await pool.fetchval(
        "select count(*) from feedback where project_id = $1", project.config.id
    ) == 0
