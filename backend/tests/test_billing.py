"""Billing wired into the render flow.

The unit-level guarantees of the ledger itself (atomic spend, idempotency,
one refund per project) are covered in test_credits.py. What's tested here
is the wiring: that submitting a render actually charges, that a failed
render actually gives the credits back, that a crash mid-render doesn't
leave the user paying for nothing — and that none of it happens on a
self-hosted install.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import current_user_id
from app.api.routes import credits as credits_route
from app.api.routes import projects as projects_route
from app.api.routes import render as render_route
from app.schemas.project import Project, ProjectStatus, VideoLength, VisualMode
from app.services import credits, db, project_store, render_manager
from app.services.media_tokens import MediaTokenSigner

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)


class FakeQueue:
    """Stands in for RenderTaskQueue so submitting a project records the
    intent instead of starting a real multi-minute render."""

    def __init__(self) -> None:
        self.submitted: list[Project] = []

    async def submit(self, project: Project) -> None:
        self.submitted.append(project)


@pytest.fixture(scope="module")
async def pool():
    # Goes through db.connect rather than asyncpg directly: the refund and
    # reconcile paths reach for db.optional_pool(), so the module-level
    # pool has to be the one these tests are using.
    try:
        p = await db.connect(TEST_DSN, min_size=1, max_size=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres at {TEST_DSN}: {exc}")
    await db.apply_migrations(p)
    yield p
    await db.disconnect()


@pytest.fixture
async def user(pool):
    return str(
        await pool.fetchval(
            "insert into app_users (email) values ($1) returning id",
            f"{uuid.uuid4()}@example.test",
        )
    )


def _build_app(pool, user_id: str | None) -> tuple[FastAPI, FakeQueue]:
    """An app wired the way the hosted product is, minus the lifespan.

    The real lifespan would start render workers, and these tests must not
    trigger an actual render.
    """
    app = FastAPI()
    app.include_router(projects_route.router)
    app.include_router(credits_route.router)
    app.include_router(render_route.router)

    queue = FakeQueue()
    app.state.db_pool = pool
    app.state.render_queue = queue
    app.state.media_signer = MediaTokenSigner("test-secret", ttl_s=900)
    app.dependency_overrides[current_user_id] = lambda: user_id
    return app, queue


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _payload(**kwargs) -> dict:
    return {"topic": "why the sky is blue", **kwargs}


@pytest.fixture(autouse=True)
def _postgres_backend(pool):
    """Point the module-level project_store facade at the test database,
    since the routes go through it rather than taking a store argument."""
    project_store.configure(pool)
    yield
    project_store.configure(None)


# --- charging on submit --------------------------------------------------


async def test_submitting_a_render_charges_the_user(pool, user):
    await credits.grant(pool, user, 20)
    app, queue = _build_app(pool, user)

    async with _client(app) as client:
        response = await client.post("/api/projects", json=_payload())

    assert response.status_code == 201
    # fast_hybrid (3) x short (1)
    assert response.json()["credits_cost"] == 3
    assert await credits.balance(pool, user) == 17
    assert len(queue.submitted) == 1


async def test_cost_scales_with_what_the_render_actually_costs(pool, user):
    """A long AI-video render must not cost the same as a short stock one —
    the compute difference between them is more than an order of magnitude."""
    await credits.grant(pool, user, 100)
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        cheap = await client.post(
            "/api/projects",
            json=_payload(visual_mode=VisualMode.STOCK_MEDIA.value,
                          video_length=VideoLength.SHORT.value),
        )
        dear = await client.post(
            "/api/projects",
            json=_payload(visual_mode=VisualMode.AI_VIDEO.value,
                          video_length=VideoLength.LONG.value),
        )

    assert cheap.json()["credits_cost"] == 1
    assert dear.json()["credits_cost"] == 30
    assert await credits.balance(pool, user) == 100 - 1 - 30


async def test_render_is_refused_when_credits_run_out(pool, user):
    await credits.grant(pool, user, 2)  # a fast_hybrid short costs 3
    app, queue = _build_app(pool, user)

    async with _client(app) as client:
        response = await client.post("/api/projects", json=_payload())

    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["error"] == "insufficient_credits"
    assert detail["balance"] == 2
    assert detail["required"] == 3

    # Nothing charged, nothing queued, and no half-created project left behind.
    assert await credits.balance(pool, user) == 2
    assert queue.submitted == []


async def test_a_refused_render_leaves_no_project(pool, user):
    """The user shouldn't find a phantom draft in their list for a render
    that was never accepted."""
    await credits.grant(pool, user, 1)
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        assert (await client.post("/api/projects", json=_payload())).status_code == 402
        listed = await client.get("/api/projects")

    assert listed.json() == []


# --- self-hosted: no user, no charge ------------------------------------


async def test_self_hosted_renders_are_free(pool):
    """No authenticated user means no billing, even though a database
    happens to be configured. Self-hosting must not require credits."""
    app, queue = _build_app(pool, None)

    async with _client(app) as client:
        response = await client.post("/api/projects", json=_payload())

    assert response.status_code == 201
    assert response.json()["credits_cost"] == 0
    assert len(queue.submitted) == 1
    assert await pool.fetchval("select count(*) from credit_entries where project_id = $1",
                               response.json()["config"]["id"]) == 0


async def test_credits_endpoint_reports_disabled_without_a_user(pool):
    app, _ = _build_app(pool, None)
    async with _client(app) as client:
        body = (await client.get("/api/credits")).json()

    # Not "balance: 0" — the UI needs to tell "free" apart from "broke".
    assert body["enabled"] is False


async def test_credits_endpoint_reports_balance_and_history(pool, user):
    await credits.grant(pool, user, 10, note="signup bonus")
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        await client.post("/api/projects", json=_payload())
        body = (await client.get("/api/credits")).json()

    assert body["enabled"] is True
    assert body["balance"] == 7
    reasons = [e["reason"] for e in body["entries"]]
    assert reasons == ["render", "grant"]  # newest first
    assert body["pricing"]["fast_hybrid:short"] == 3


# --- refunds -------------------------------------------------------------


async def test_a_failed_render_is_refunded(pool, user):
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]
    assert await credits.balance(pool, user) == 17

    await render_manager._refund_failed_render(project_id, reason="ffmpeg exploded")

    assert await credits.balance(pool, user) == 20


async def test_a_failed_render_is_refunded_only_once(pool, user):
    """The failure handler and the startup reconciler can both fire for the
    same project; between them they must pay out once."""
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    await render_manager._refund_failed_render(project_id, reason="boom")
    await render_manager._refund_failed_render(project_id, reason="boom again")

    assert await credits.balance(pool, user) == 20


async def test_a_successful_render_is_not_refunded(pool, user):
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    await project_store.update_project(
        project_id, status=ProjectStatus.COMPLETE, output_path="/tmp/final.mp4"
    )
    assert await credits.balance(pool, user) == 17


# --- crash recovery ------------------------------------------------------


async def test_renders_interrupted_by_a_restart_are_refunded_and_failed(pool, user):
    """The scenario: a paid render is in flight, the process dies. Nothing
    will ever move it forward, so leaving it alone means the user paid for
    a video that stays 'rendering' forever."""
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    # The state a killed worker leaves behind.
    await project_store.update_project(project_id, status=ProjectStatus.RENDERING)
    assert await credits.balance(pool, user) == 17

    recovered = await render_manager.reconcile_interrupted_renders()

    assert recovered >= 1
    assert await credits.balance(pool, user) == 20
    project = await project_store.get_project(project_id)
    assert project.status == ProjectStatus.FAILED
    assert "interrupted" in project.error


async def test_reconciler_leaves_finished_renders_alone(pool, user):
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)

    async with _client(app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]
    await project_store.update_project(
        project_id, status=ProjectStatus.COMPLETE, output_path="/tmp/final.mp4"
    )

    await render_manager.reconcile_interrupted_renders()

    project = await project_store.get_project(project_id)
    assert project.status == ProjectStatus.COMPLETE
    assert await credits.balance(pool, user) == 17


# --- ownership -----------------------------------------------------------


async def test_projects_are_scoped_to_their_owner(pool, user):
    await credits.grant(pool, user, 20)
    owner_app, _ = _build_app(pool, user)
    async with _client(owner_app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    other = str(
        await pool.fetchval(
            "insert into app_users (email) values ($1) returning id",
            f"{uuid.uuid4()}@example.test",
        )
    )
    intruder_app, _ = _build_app(pool, other)
    async with _client(intruder_app) as client:
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
        assert (await client.get("/api/projects")).json() == []
        assert (await client.delete(f"/api/projects/{project_id}")).status_code == 404

    # And the intruder's 404 didn't actually delete anything.
    assert await project_store.get_project(project_id) is not None


async def test_an_owned_project_is_not_reachable_without_authentication(pool, user):
    """An unauthenticated caller looks like a self-hosted operator. It must
    still not be able to read a project that belongs to someone."""
    await credits.grant(pool, user, 20)
    owner_app, _ = _build_app(pool, user)
    async with _client(owner_app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    anon_app, _ = _build_app(pool, None)
    async with _client(anon_app) as client:
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
        assert (await client.get(f"/api/projects/{project_id}/download")).status_code == 404


async def test_reconciler_does_not_steal_a_render_that_just_finished(pool, user, monkeypatch):
    """The race seen live: the reconciler reads `rendering`, the pipeline
    finishes, and only then does the reconciler write. A blind write left a
    `complete` render carrying a "was interrupted" error — and refunded a
    video the user had already received.

    The stale read is injected rather than ordered, because reconcile does
    its own listing: without this the project is already `complete` by the
    time it looks, the reconciler correctly does nothing, and the test
    proves nothing at all.
    """
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)
    async with _client(app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    # The pipeline has already finished by the time the reconciler writes...
    await project_store.update_project(
        project_id, status=ProjectStatus.COMPLETE, output_path="/tmp/final.mp4", error=None
    )
    # ...but the reconciler is working from a listing taken before that.
    monkeypatch.setattr(project_store, "list_interrupted", lambda: _returns([project_id]))

    await render_manager.reconcile_interrupted_renders()

    project = await project_store.get_project(project_id)
    assert project.status == ProjectStatus.COMPLETE, "reconciler overwrote a finished render"
    assert project.error is None, "finished render left carrying an interruption error"
    assert await credits.balance(pool, user) == 17, "refunded a video the user actually got"


async def _returns(value):
    return value


async def test_a_genuinely_abandoned_render_is_still_recovered(pool, user):
    """The guard must not stop the reconciler doing its job."""
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)
    async with _client(app) as client:
        project_id = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    await project_store.update_project(project_id, status=ProjectStatus.RENDERING)
    await render_manager.reconcile_interrupted_renders()

    project = await project_store.get_project(project_id)
    assert project.status == ProjectStatus.FAILED
    assert await credits.balance(pool, user) == 20


# --- signed media URLs ---------------------------------------------------


async def _completed_project(pool, user, video: Path):
    """A finished project whose video really exists on disk.

    The file has to be real: without it a leak shows up as "file not found"
    instead of the request succeeding, which hides whether the access check
    ran at all.
    """
    app, _ = _build_app(pool, user)
    async with _client(app) as client:
        pid = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]
    video.write_bytes(b"not really an mp4, but it exists")
    await project_store.update_project(
        pid, status=ProjectStatus.COMPLETE, output_path=str(video)
    )
    return app, pid


async def test_the_owner_gets_a_playable_url(pool, user, tmp_path):
    await credits.grant(pool, user, 20)
    app, pid = await _completed_project(pool, user, tmp_path / "a.mp4")

    async with _client(app) as client:
        body = (await client.get(f"/api/projects/{pid}/media-url")).json()
        played = await client.get(body["url"])

    assert body["url"].startswith(f"/api/projects/{pid}/download?token=")
    assert played.status_code == 200
    assert played.content == b"not really an mp4, but it exists"


async def test_a_stranger_cannot_mint_a_url_for_someone_elses_video(pool, user, tmp_path):
    """Ownership is enforced where it can be — on the request that mints
    the link, which is the one that can carry an Authorization header."""
    await credits.grant(pool, user, 20)
    _, pid = await _completed_project(pool, user, tmp_path / "a.mp4")

    intruder = str(await pool.fetchval(
        "insert into app_users (email) values ($1) returning id", f"{uuid.uuid4()}@example.test"))
    app, _ = _build_app(pool, intruder)
    async with _client(app) as client:
        assert (await client.get(f"/api/projects/{pid}/media-url")).status_code == 404


async def test_a_token_for_one_video_does_not_open_another(pool, user, tmp_path):
    """The failure that would matter most: one shared link unlocking the
    whole service."""
    await credits.grant(pool, user, 40)
    app, mine = await _completed_project(pool, user, tmp_path / "mine.mp4")

    other_user = str(await pool.fetchval(
        "insert into app_users (email) values ($1) returning id", f"{uuid.uuid4()}@example.test"))
    await credits.grant(pool, other_user, 20)
    _, theirs = await _completed_project(pool, other_user, tmp_path / "theirs.mp4")

    async with _client(app) as client:
        url = (await client.get(f"/api/projects/{mine}/media-url")).json()["url"]
        token = url.split("token=")[1]
        stolen = await client.get(f"/api/projects/{theirs}/download?token={token}")

    assert stolen.status_code == 403


async def test_a_tampered_token_is_refused(pool, user, tmp_path):
    await credits.grant(pool, user, 20)
    app, pid = await _completed_project(pool, user, tmp_path / "a.mp4")

    async with _client(app) as client:
        url = (await client.get(f"/api/projects/{pid}/media-url")).json()["url"]
        token = url.split("token=")[1]
        expiry, signature = token.split(".", 1)
        forged = f"{int(expiry) + 999999}.{signature}"
        response = await client.get(f"/api/projects/{pid}/download?token={forged}")

    assert response.status_code == 403


async def test_download_without_any_credential_is_still_refused(pool, user, tmp_path):
    """The gap this whole mechanism exists to close: before it, an
    unauthenticated GET on the download URL served an owned video."""
    await credits.grant(pool, user, 20)
    _, pid = await _completed_project(pool, user, tmp_path / "a.mp4")

    anon, _ = _build_app(pool, None)
    async with _client(anon) as client:
        assert (await client.get(f"/api/projects/{pid}/download")).status_code == 404


async def test_a_media_url_is_refused_before_the_render_finishes(pool, user):
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)
    async with _client(app) as client:
        pid = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]
        assert (await client.get(f"/api/projects/{pid}/media-url")).status_code == 409


# --- render-progress socket ----------------------------------------------
#
# The socket's own auth logic lives in test_progress_socket.py: driving a
# real WebSocket needs TestClient, which runs its own event loop and can't
# share this module's asyncpg pool.


async def test_a_stranger_cannot_get_a_stream_token(pool, user):
    await credits.grant(pool, user, 20)
    app, _ = _build_app(pool, user)
    async with _client(app) as client:
        pid = (await client.post("/api/projects", json=_payload())).json()["config"]["id"]

    other = str(await pool.fetchval(
        "insert into app_users (email) values ($1) returning id", f"{uuid.uuid4()}@example.test"))
    intruder, _ = _build_app(pool, other)
    async with _client(intruder) as client:
        assert (await client.get(f"/api/projects/{pid}/stream-token")).status_code == 404
