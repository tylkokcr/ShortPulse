"""Paying for a scene re-roll.

The first thing in this product that takes money after the render is
over, which makes it the first place several ledger assumptions stop
holding: the charge is not part of the render's price, it can happen more
than once for one project, and it has to be given back if the picture
never arrives.

The work itself is stubbed out — test_scene_regeneration.py owns that.
What is under test here is who gets charged, how much, how often, and
what happens when it fails.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import current_user_id
from app.api.routes import projects as projects_route
from app.schemas.project import (
    Project,
    ProjectConfig,
    ProjectStatus,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptOutput,
    VisualMode,
)
from app.services import credits, db, project_lock, project_store, regeneration
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
    project_lock._held.clear()


@pytest.fixture
async def user(pool):
    return str(
        await pool.fetchval(
            "insert into app_users (email) values ($1) returning id",
            f"{uuid.uuid4()}@example.test",
        )
    )


def _scenes(count: int = 3) -> list[Scene]:
    return [
        Scene(
            index=i,
            duration_s=4.0,
            visual=SceneVisual(prompt=f"scene {i}"),
            audio=SceneAudio(voiceover_line=f"line {i}", duration_ms=4000),
        )
        for i in range(count)
    ]


async def _finished_project(user_id: str, mode=VisualMode.FAST_HYBRID) -> Project:
    config = ProjectConfig(topic="quiet people", visual_mode=mode)
    await project_store.create_project(config, user_id)
    return await project_store.update_project(
        config.id,
        status=ProjectStatus.COMPLETE,
        script=ScriptOutput(
            topic="quiet people", hook="h", scenes=_scenes(), total_duration_s=12.0
        ),
        output_path="/tmp/final.mp4",
    )


def _build_app(pool, user_id: str | None):
    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = pool
    app.state.render_queue = None
    app.state.media_signer = MediaTokenSigner("test-secret", ttl_s=900)
    app.dependency_overrides[current_user_id] = lambda: user_id
    return app


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def stub_work(monkeypatch):
    """Let the route through without touching Replicate or ffmpeg.

    Availability is stubbed too: it asks the filesystem, and what it
    answers is covered where the filesystem is set up properly.
    """
    calls: list[tuple[str, int]] = []

    def available(project):
        return True, None

    async def regenerate(project, scene_index, settings, **kwargs):
        calls.append((project.config.id, scene_index))
        project.script.scenes[scene_index].visual.revision += 1
        return "/tmp/final.mp4"

    monkeypatch.setattr(regeneration, "availability", available)
    monkeypatch.setattr(regeneration, "regenerate_scene", regenerate)
    return calls


async def _regenerate(app, project_id: str, index: int = 1, **body):
    async with _client(app) as client:
        return await client.post(
            f"/api/projects/{project_id}/scenes/{index}/regenerate", json=body
        )


# --- what it costs -------------------------------------------------------


async def test_a_re_roll_costs_one_credit(pool, user, stub_work):
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)

    response = await _regenerate(_build_app(pool, user), project.config.id)

    assert response.status_code == 200
    assert await credits.balance(pool, user) == 19


async def test_re_rolling_the_same_scene_twice_charges_twice(pool, user, stub_work):
    """A second attempt is a second picture and a second re-encode. The
    idempotency key has to carry the revision or it would be free."""
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)
    app = _build_app(pool, user)

    await _regenerate(app, project.config.id)
    await _regenerate(app, project.config.id)

    assert await credits.balance(pool, user) == 18


async def test_the_charge_is_not_part_of_the_render_refund(pool, user, stub_work):
    """The invariant migration 0005 exists for, from the API side: refund
    the render and the re-rolls the customer kept stay bought."""
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)
    await credits.spend(
        pool, user, 9, project_id=project.config.id, idempotency_key=f"render:{project.config.id}"
    )
    await _regenerate(_build_app(pool, user), project.config.id)
    assert await credits.balance(pool, user) == 10

    refunded = await credits.refund_project(pool, project.config.id)

    assert refunded == 9
    assert await credits.balance(pool, user) == 19


async def test_an_account_that_cannot_afford_it_is_told_before_anything_runs(
    pool, user, stub_work
):
    """stock_media so the purchase gate isn't what answers — this is about
    an empty balance, and the two 402s are different sentences."""
    project = await _finished_project(user, mode=VisualMode.STOCK_MEDIA)

    response = await _regenerate(_build_app(pool, user), project.config.id)

    assert response.status_code == 402
    assert response.json()["detail"]["error"] == "insufficient_credits"
    assert stub_work == [], "the generator ran for an account with no credits"


async def test_self_hosting_is_free(pool, stub_work):
    """No user, no ledger, no charge — the same rule as every other paid
    action here."""
    project = await _finished_project(None)

    response = await _regenerate(_build_app(pool, None), project.config.id)

    assert response.status_code == 200
    assert await pool.fetchval(
        "select count(*) from credit_entries where project_id = $1", project.config.id
    ) == 0


async def test_the_free_grant_cannot_buy_a_generated_re_roll(pool, user, stub_work):
    """Grant-funded accounts are held to a gate at least as strict as the
    one at render time.

    This was nearly unreachable when a fast_hybrid project implied a
    purchase. The free trial made it the ordinary path: everyone who takes
    the one free generated video lands here the moment they try to fix a
    scene in it, which is why credits.REROLL_PURCHASE_REQUIRED_REASON says
    what it says rather than repeating the render-time wording.
    """
    await credits.grant(pool, user, 20)  # a grant, not a purchase
    project = await _finished_project(user)

    response = await _regenerate(_build_app(pool, user), project.config.id)

    assert response.status_code == 402
    assert response.json()["detail"]["error"] == "purchase_required"
    assert await credits.balance(pool, user) == 20


async def test_a_stock_re_roll_needs_no_purchase(pool, user, stub_work):
    """stock_media is what the grant covers, so fixing one of its scenes
    is covered too."""
    await credits.grant(pool, user, 20)
    project = await _finished_project(user, mode=VisualMode.STOCK_MEDIA)

    response = await _regenerate(_build_app(pool, user), project.config.id)

    assert response.status_code == 200
    assert await credits.balance(pool, user) == 19


# --- when it goes wrong --------------------------------------------------


async def test_a_failed_re_roll_gives_the_credit_back(pool, user, monkeypatch):
    """Charged first so the user learns immediately, compensated after —
    an appended entry, never an edit to the debit."""
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)

    async def explode(*args, **kwargs):
        raise RuntimeError("replicate said no")

    monkeypatch.setattr(regeneration, "availability", lambda p: (True, None))
    monkeypatch.setattr(regeneration, "regenerate_scene", explode)

    response = await _regenerate(_build_app(pool, user), project.config.id)

    assert response.status_code == 502
    assert await credits.balance(pool, user) == 20


async def test_a_retry_after_a_failure_charges_cleanly(pool, user, monkeypatch, stub_work):
    """The compensation is keyed on the revision that failed, and the
    revision only advances on success — so the retry is a fresh charge
    rather than a replay of the refunded one."""
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)
    fail = True

    async def flaky(project_, scene_index, settings, **kwargs):
        if fail:
            raise RuntimeError("transient")
        project_.script.scenes[scene_index].visual.revision += 1
        return "/tmp/final.mp4"

    monkeypatch.setattr(regeneration, "regenerate_scene", flaky)
    app = _build_app(pool, user)

    await _regenerate(app, project.config.id)
    assert await credits.balance(pool, user) == 20, "the failed attempt was not given back"

    fail = False
    await _regenerate(app, project.config.id)

    assert await credits.balance(pool, user) == 19


async def test_a_scene_that_does_not_exist_is_refused_before_charging(pool, user, stub_work):
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)

    response = await _regenerate(_build_app(pool, user), project.config.id, index=99)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "no_such_scene"
    assert await credits.balance(pool, user) == 20


async def test_a_swept_project_explains_itself(pool, user, monkeypatch):
    """Every video rendered before this feature existed lands here."""
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)
    monkeypatch.setattr(
        regeneration, "availability", lambda p: (False, "The working files ... cleaned up")
    )

    response = await _regenerate(_build_app(pool, user), project.config.id)

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "not_regenerable"
    assert await credits.balance(pool, user) == 20


async def test_two_at_once_on_one_project_is_refused_and_charged_once(
    pool, user, monkeypatch
):
    """Both rewrite concatenated.mp4, and both would read the same
    revision — so without the lock the second one is free *and* corrupting."""
    await credits.grant(pool, user, 20, reason="purchase")
    project = await _finished_project(user)
    started = asyncio.Event()

    async def slow(project_, scene_index, settings, **kwargs):
        started.set()
        await asyncio.sleep(0.05)
        return "/tmp/final.mp4"

    monkeypatch.setattr(regeneration, "availability", lambda p: (True, None))
    monkeypatch.setattr(regeneration, "regenerate_scene", slow)
    app = _build_app(pool, user)

    async def second():
        await started.wait()
        return await _regenerate(app, project.config.id)

    first_response, second_response = await asyncio.gather(
        _regenerate(app, project.config.id), second()
    )

    assert {first_response.status_code, second_response.status_code} == {200, 409}
    busy = first_response if first_response.status_code == 409 else second_response
    assert busy.json()["detail"]["error"] == "busy"
    assert await credits.balance(pool, user) == 19
