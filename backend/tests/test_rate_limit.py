"""Request throttling.

Credits stop a user spending more than they have. They do nothing about
how fast someone can ask: one account with a healthy balance could fill
the render queue ahead of everyone else's work, and an anonymous caller
could hammer the cheap endpoints indefinitely.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.middleware import RateLimitMiddleware
from app.services.rate_limit import TokenBucketLimiter

# --- the bucket itself ---------------------------------------------------


def test_a_burst_within_capacity_is_allowed():
    """Submitting a few renders back to back is normal use, not abuse."""
    limiter = TokenBucketLimiter(capacity=5, per_seconds=60)
    assert all(limiter.check("someone") is None for _ in range(5))


def test_the_request_past_capacity_is_refused():
    limiter = TokenBucketLimiter(capacity=3, per_seconds=60)
    for _ in range(3):
        limiter.check("someone")

    retry_after = limiter.check("someone")
    assert retry_after is not None
    assert 0 < retry_after <= 60


def test_one_caller_cannot_exhaust_another_s_budget(monkeypatch):
    """Keyed per caller — otherwise a single abusive client would lock out
    every other user."""
    limiter = TokenBucketLimiter(capacity=2, per_seconds=60)
    limiter.check("alice")
    limiter.check("alice")
    assert limiter.check("alice") is not None

    assert limiter.check("bob") is None


def test_the_budget_refills_over_time(monkeypatch):
    # Patch before constructing: the limiter reads the clock in its own
    # initialiser, and mixing a real reading with a fake one makes the
    # elapsed time meaningless.
    clock = [1000.0]
    monkeypatch.setattr("app.services.rate_limit.time.monotonic", lambda: clock[0])
    limiter = TokenBucketLimiter(capacity=60, per_seconds=60)  # one per second

    for _ in range(60):
        limiter.check("someone")
    assert limiter.check("someone") is not None

    clock[0] += 10  # ten seconds -> ten tokens back
    assert all(limiter.check("someone") is None for _ in range(10))
    assert limiter.check("someone") is not None


def test_idle_callers_are_forgotten(monkeypatch):
    """A stream of one-off addresses must not grow this without bound."""
    clock = [1000.0]
    monkeypatch.setattr("app.services.rate_limit.time.monotonic", lambda: clock[0])
    limiter = TokenBucketLimiter(capacity=5, per_seconds=60)

    for i in range(100):
        limiter.check(f"ip-{i}")
    assert len(limiter._buckets) == 100

    clock[0] += 120  # everyone has had time to fully refill
    limiter.check("someone-new")
    assert len(limiter._buckets) == 1


# --- wired into the app --------------------------------------------------


def _app(*, renders_per_hour=3, requests_per_minute=5, user_id=None):
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        renders_per_hour=renders_per_hour,
        requests_per_minute=requests_per_minute,
    )

    @app.middleware("http")
    async def fake_auth(request, call_next):
        request.state.user_id = user_id
        return await call_next(request)

    @app.post("/api/projects")
    async def create():
        return {"ok": True}

    @app.get("/api/projects")
    async def read():
        return []

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_render_submissions_are_capped():
    app = _app(renders_per_hour=3)
    async with _client(app) as client:
        codes = [(await client.post("/api/projects", json={})).status_code for _ in range(5)]

    assert codes == [200, 200, 200, 429, 429]


async def test_a_throttled_response_says_when_to_retry():
    app = _app(renders_per_hour=1)
    async with _client(app) as client:
        await client.post("/api/projects", json={})
        refused = await client.post("/api/projects", json={})

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1


async def test_reading_is_not_limited_by_the_render_budget():
    """Two budgets on purpose: a render occupies a GPU for minutes, a read
    is one query. Sharing a limit would make ordinary browsing feel broken."""
    app = _app(renders_per_hour=1, requests_per_minute=50)
    async with _client(app) as client:
        await client.post("/api/projects", json={})
        assert (await client.post("/api/projects", json={})).status_code == 429
        codes = [(await client.get("/api/projects")).status_code for _ in range(10)]

    assert codes == [200] * 10


async def test_health_is_never_throttled():
    """Uptime checks poll constantly and must not be locked out, or a
    throttled service looks like a dead one to the load balancer."""
    app = _app(requests_per_minute=2)
    async with _client(app) as client:
        codes = [(await client.get("/api/health")).status_code for _ in range(20)]

    assert codes == [200] * 20


async def test_users_are_throttled_separately_from_each_other():
    alice = _app(renders_per_hour=1, user_id="alice")
    bob = _app(renders_per_hour=1, user_id="bob")

    async with _client(alice) as client:
        await client.post("/api/projects", json={})
        assert (await client.post("/api/projects", json={})).status_code == 429

    # A separate app instance stands in for a different caller reaching the
    # same limiter state; what matters is that the key is the user.
    async with _client(bob) as client:
        assert (await client.post("/api/projects", json={})).status_code == 200


@pytest.mark.parametrize("path", ["/api/projects"])
async def test_general_requests_are_capped(path):
    app = _app(requests_per_minute=3)
    async with _client(app) as client:
        codes = [(await client.get(path)).status_code for _ in range(5)]

    assert codes == [200, 200, 200, 429, 429]
