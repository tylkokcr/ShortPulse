"""Authentication wired into the real request path.

test_supabase_auth.py proves the verifier accepts and rejects the right
tokens. This proves the rest of the chain: that a verified token becomes
the identity the billing layer charges, that a bad token is refused rather
than quietly downgraded to anonymous, and that an anonymous request still
works on a self-hosted install.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.api.middleware import SupabaseAuthMiddleware
from app.api.routes import credits as credits_route
from app.api.routes import music as music_route
from app.api.routes import projects as projects_route
from app.api.routes import voices as voices_route
from app.services import credits, db, project_store
from app.services.media_tokens import MediaTokenSigner
from app.services.supabase_auth import SupabaseTokenVerifier
from tests.conftest import PROJECT_URL, Signer

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)


class FakeQueue:
    def __init__(self) -> None:
        self.submitted = []

    async def submit(self, project) -> None:
        self.submitted.append(project)


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


def _build_app(pool, jwks, *, require_auth=False, signup_grant=0, with_verifier=True):
    app = FastAPI()
    app.include_router(projects_route.router)
    app.include_router(credits_route.router)
    app.include_router(voices_route.router)
    app.include_router(music_route.router)
    app.add_middleware(
        SupabaseAuthMiddleware,
        verifier=SupabaseTokenVerifier(PROJECT_URL, http_client=jwks.client())
        if with_verifier
        else None,
        require_auth=require_auth,
        signup_grant=signup_grant,
    )
    queue = FakeQueue()
    app.state.db_pool = pool
    app.state.render_queue = queue
    app.state.media_signer = MediaTokenSigner("test-secret", ttl_s=900)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app, queue


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# stock_media explicitly, not the default mode. These accounts are funded
# by the signup grant, which only buys stock footage (credits.FREE_TIER_MODES),
# and this file is about which identity gets billed — not about which modes
# that identity has paid for. test_free_tier_modes.py owns the latter.
PAYLOAD = {"topic": "why the sky is blue", "visual_mode": "stock_media"}


@pytest.fixture(autouse=True)
def _stock_media_is_available(monkeypatch):
    """Say that the mode PAYLOAD asks for can actually run here.

    The routes read get_settings(), which loads whatever .env this machine
    has. Left implicit, every test below would really be asserting that
    the developer happens to own a Pexels key — and would start returning
    422 on a machine without one, for a reason having nothing to do with
    authentication.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "pexels_api_key", "test-key")


# --- a verified token becomes the billed identity ------------------------


async def test_a_valid_token_identifies_and_bills_the_right_user(pool, jwks, signer):
    """The whole point of the chain: the user in the token is the user
    whose balance moves and who owns the resulting project."""
    user_id = str(uuid.uuid4())
    app, queue = _build_app(pool, jwks, signup_grant=20)

    async with _client(app) as client:
        created = await client.post(
            "/api/projects", json=PAYLOAD, headers=_auth(signer.token(sub=user_id))
        )

    assert created.status_code == 201
    assert created.json()["credits_cost"] == 1  # stock_media short
    assert await credits.balance(pool, user_id) == 19
    assert len(queue.submitted) == 1
    assert await project_store.owner_of(created.json()["config"]["id"]) == user_id


async def test_anonymous_listing_never_exposes_owned_projects(pool, jwks, signer):
    """Found in a live end-to-end run: single-project reads checked
    ownership but the listing didn't, so an unauthenticated GET /api/projects
    returned every user's work."""
    user_id = str(uuid.uuid4())
    app, _ = _build_app(pool, jwks, signup_grant=20)
    async with _client(app) as client:
        owned = (await client.post(
            "/api/projects", json=PAYLOAD, headers=_auth(signer.token(sub=user_id))
        )).json()["config"]["id"]

    anon_app, _ = _build_app(pool, jwks)
    async with _client(anon_app) as client:
        listed = (await client.get("/api/projects")).json()

    ids = {p["config"]["id"] for p in listed}
    assert owned not in ids, "owned project exposed to an unauthenticated caller"


async def test_anonymous_listing_still_shows_self_hosted_projects(pool, jwks):
    """The self-hosted install has no accounts, so its own unowned projects
    must stay visible — the fix above must not empty that list."""
    app, _ = _build_app(pool, jwks)
    async with _client(app) as client:
        mine = (await client.post("/api/projects", json=PAYLOAD)).json()["config"]["id"]
        listed = (await client.get("/api/projects")).json()

    assert mine in {p["config"]["id"] for p in listed}


async def test_a_user_only_sees_their_own_projects(pool, jwks, signer):
    alice, bob = str(uuid.uuid4()), str(uuid.uuid4())
    app, _ = _build_app(pool, jwks, signup_grant=20)

    async with _client(app) as client:
        await client.post("/api/projects", json=PAYLOAD, headers=_auth(signer.token(sub=alice)))
        bobs_list = await client.get("/api/projects", headers=_auth(signer.token(sub=bob)))

    assert bobs_list.json() == []


# --- bad credentials are refused, never downgraded -----------------------


async def test_an_invalid_token_is_refused_rather_than_treated_as_anonymous(pool, jwks):
    """The dangerous failure mode: silently falling back to anonymous would
    make an expired token a free render on a paid deployment."""
    attacker = Signer(kid="key-1")  # not the key in our JWKS
    app, queue = _build_app(pool, jwks)

    async with _client(app) as client:
        response = await client.post(
            "/api/projects", json=PAYLOAD, headers=_auth(attacker.token())
        )

    assert response.status_code == 401
    assert queue.submitted == []


async def test_a_token_is_refused_when_the_deployment_cannot_check_it(pool, jwks, signer):
    """Credentials presented to a deployment with no verifier configured.
    Ignoring them would run the request as anonymous."""
    app, queue = _build_app(pool, jwks, with_verifier=False)

    async with _client(app) as client:
        response = await client.post(
            "/api/projects", json=PAYLOAD, headers=_auth(signer.token())
        )

    assert response.status_code == 401
    assert queue.submitted == []


# --- require_auth: what makes a public deployment safe -------------------


async def test_anonymous_requests_are_refused_when_auth_is_required(pool, jwks):
    app, queue = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        response = await client.post("/api/projects", json=PAYLOAD)

    assert response.status_code == 401
    assert queue.submitted == []


async def test_health_stays_reachable_when_auth_is_required(pool, jwks):
    """Uptime checks and load balancers don't carry credentials."""
    app, _ = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        assert (await client.get("/api/health")).status_code == 200


async def test_anonymous_requests_work_when_auth_is_not_required(pool, jwks):
    """The self-hosted install: no accounts, no billing, still works."""
    app, queue = _build_app(pool, jwks, require_auth=False)

    async with _client(app) as client:
        response = await client.post("/api/projects", json=PAYLOAD)

    assert response.status_code == 201
    assert response.json()["credits_cost"] == 0
    assert len(queue.submitted) == 1


# --- first sight of a user ----------------------------------------------


async def test_a_new_user_is_mirrored_and_granted_once(pool, jwks, signer):
    """The grant is real compute given away, so a user reconnecting must
    not top themselves up by signing in again."""
    user_id = str(uuid.uuid4())
    app, _ = _build_app(pool, jwks, signup_grant=25)
    token = signer.token(sub=user_id, email="new@example.test")

    async with _client(app) as client:
        for _ in range(3):
            await client.get("/api/credits", headers=_auth(token))

    assert await pool.fetchval("select email from app_users where id = $1", user_id) == "new@example.test"
    assert await credits.balance(pool, user_id) == 25
    assert await pool.fetchval(
        "select count(*) from credit_entries where user_id = $1 and reason = 'grant'", user_id
    ) == 1


async def test_no_credits_are_given_away_by_default(pool, jwks, signer):
    """signup_credit_grant defaults to 0 — free credits should never be an
    accident."""
    user_id = str(uuid.uuid4())
    app, _ = _build_app(pool, jwks)

    async with _client(app) as client:
        body = (await client.get("/api/credits", headers=_auth(signer.token(sub=user_id)))).json()

    assert body["enabled"] is True
    assert body["balance"] == 0


async def test_a_returning_user_keeps_their_balance(pool, jwks, signer):
    """Re-authenticating must not reset an existing account."""
    user_id = str(uuid.uuid4())
    app, _ = _build_app(pool, jwks, signup_grant=10)
    token = signer.token(sub=user_id)

    async with _client(app) as client:
        await client.get("/api/credits", headers=_auth(token))
        await client.post("/api/projects", json=PAYLOAD, headers=_auth(token))
        body = (await client.get("/api/credits", headers=_auth(token))).json()

    assert body["balance"] == 9  # 10 granted, one stock_media short spent


async def test_two_users_sharing_an_email_both_work(pool, jwks, signer):
    """Deleting a Supabase account and signing up again with the same
    address yields a new id and the same email, which must still work
    through the full request path.

    Note this cannot detect a reverted migration 0002 on its own: the pool
    fixture re-applies migrations, so the constraint would be dropped again
    before the test ran. test_migrations.py is what pins 0002, against a
    database built from nothing.
    """
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    app, _ = _build_app(pool, jwks)
    email = f"recycled-{uuid.uuid4()}@example.test"

    async with _client(app) as client:
        a = await client.get("/api/credits", headers=_auth(signer.token(sub=first, email=email)))
        b = await client.get("/api/credits", headers=_auth(signer.token(sub=second, email=email)))

    assert a.status_code == 200
    assert b.status_code == 200


# --- the video the customer paid for -------------------------------------
#
# test_billing.py covers who is allowed to mint a media URL and whose
# video it opens, but it builds an app without this middleware — so it
# proved the *route* right while the request never reached it. On the live
# deployment, with REQUIRE_AUTH on, a finished render was 401 in the
# browser that had just been charged nine credits for it. These go through
# the middleware, which is the only place that bug was visible.


async def test_a_signed_media_token_reaches_the_video(pool, jwks, signer):
    """A <video> element cannot send a bearer token, so the URL is the
    credential. Refusing it here makes every finished render unreachable."""
    user_id = str(uuid.uuid4())
    app, _ = _build_app(pool, jwks, require_auth=True, signup_grant=20)

    async with _client(app) as client:
        created = await client.post(
            "/api/projects", json=PAYLOAD, headers=_auth(signer.token(sub=user_id))
        )
        project_id = created.json()["config"]["id"]
        media = await client.get(
            f"/api/projects/{project_id}/media-url", headers=_auth(signer.token(sub=user_id))
        )
        token, _expires = app.state.media_signer.sign(project_id)
        response = await client.get(f"/api/projects/{project_id}/download?token={token}")

    # 409 because this project has no rendered file yet — which is the
    # point: the middleware let it through to the route, and the route
    # answered on the merits. A 401 here is the regression.
    assert response.status_code != 401
    assert media.status_code in (200, 409)


async def test_a_media_request_without_a_token_is_still_refused(pool, jwks):
    """The exemption is for requests that carry their own credential. One
    that carries nothing must not inherit it, or every finished video is
    public to anyone who can guess a project id."""
    app, _ = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        response = await client.get(f"/api/projects/{uuid.uuid4()}/download")

    assert response.status_code == 401


async def test_a_forged_media_token_is_refused_by_the_route(pool, jwks):
    """Skipping authentication is not the same as granting access: the
    signature is still checked, one project at a time."""
    app, _ = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        response = await client.get(f"/api/projects/{uuid.uuid4()}/download?token=not-a-token")

    # 403 from the route, not 401 from the middleware — the request got
    # through and was judged on its signature.
    assert response.status_code == 403


async def test_the_poster_is_reachable_the_same_way(pool, jwks):
    """The library grid renders posters in <img> tags, which have the same
    problem as <video> and were caught by the same 401."""
    project_id = str(uuid.uuid4())
    app, _ = _build_app(pool, jwks, require_auth=True)
    token, _expires = app.state.media_signer.sign(project_id)

    async with _client(app) as client:
        response = await client.get(f"/api/projects/{project_id}/poster?token={token}")

    assert response.status_code != 401


async def test_other_project_routes_stay_behind_authentication(pool, jwks):
    """The pattern is narrow on purpose. A token in the query string must
    not open the project list, the edit endpoint, or anything else."""
    app, _ = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        listing = await client.get("/api/projects?token=anything")
        one = await client.get(f"/api/projects/{uuid.uuid4()}?token=anything")
        minting = await client.get(f"/api/projects/{uuid.uuid4()}/media-url?token=anything")

    assert listing.status_code == 401
    assert one.status_code == 401
    assert minting.status_code == 401


# --- catalog samples, which no bearer token can reach --------------------
#
# The third and fourth callers found in the same position as the Stripe
# webhook and the video download: a media element fetching a URL, unable
# to attach a header. The voice preview shipped with a comment saying the
# endpoint "needs none" — true on an install with no accounts, false from
# the day REQUIRE_AUTH went on, and nothing announced the change. The
# symptom is a play button that does nothing.


async def test_a_voice_can_be_auditioned_without_a_token(pool, jwks):
    """<audio> cannot send Authorization, so an authenticated preview URL
    is an unplayable one."""
    app, _ = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        response = await client.get("/api/voices/preview?voice_id=nonexistent")

    # 404 from the route — an unknown voice — rather than 401 from here.
    # What matters is that the request arrived.
    assert response.status_code != 401


async def test_a_music_track_can_be_auditioned_without_a_token(pool, jwks):
    app, _ = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        response = await client.get("/api/music/preview?track_id=nonexistent")

    assert response.status_code != 401


async def test_the_voice_catalog_itself_still_needs_one(pool, jwks):
    """Only the sample is exempt. The list is fetched with headers like
    everything else, so exempting it would widen the hole for nothing."""
    app, _ = _build_app(pool, jwks, require_auth=True)

    async with _client(app) as client:
        response = await client.get("/api/voices")

    assert response.status_code == 401
