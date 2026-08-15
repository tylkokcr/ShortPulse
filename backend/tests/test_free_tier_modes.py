"""What the signup grant is allowed to buy.

test_visual_mode_availability.py covers the other half of the same
sentence: what the *install* can render. This one covers what the
*account* has paid to render, and the two are deliberately not the same
check — a deployment with no Replicate token must tell an operator the
token is missing, not tell a customer to buy credits for a mode no
purchase would unlock.

The rule itself is one line (FREE_TIER_MODES), so what is worth testing is
everything around it: that it does not fire on a self-hosted install, that
a purchase lifts it permanently rather than while the balance lasts, and
that a refusal costs the caller nothing.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import current_user_id
from app.api.routes import projects as projects_route
from app.api.routes import visual_modes as visual_modes_route
from app.engines import visual_engine
from app.schemas.project import VisualMode
from app.services import credits

USER = "11111111-1111-1111-1111-111111111111"


class FakePool:
    """Answers the two queries this flow makes: has this account bought
    anything, and debit it.

    A stub rather than a real ledger because these tests are about the
    branch, not about SQL — test_credits.py runs the real spend_credits()
    against a real Postgres. `purchase_checks` is kept so a test can
    assert the gate asked once rather than once per mode.
    """

    def __init__(self, purchased: bool, balance: int = 20) -> None:
        self.purchased = purchased
        self.balance = balance
        self.purchase_checks: list[str] = []

    async def fetchval(self, sql: str, *args):
        if "credit_entries" in sql:
            self.purchase_checks.append(sql)
            return self.purchased
        if "spend_credits" in sql:
            return self.balance
        raise AssertionError(f"unexpected query: {sql}")


class FakeQueue:
    def __init__(self) -> None:
        self.submitted: list = []

    async def submit(self, project) -> None:
        self.submitted.append(project)


def _app(router, *, pool, user_id: str | None):
    app = FastAPI()
    app.include_router(router)
    app.state.db_pool = pool
    app.state.render_queue = FakeQueue()
    app.dependency_overrides[current_user_id] = lambda: user_id
    return app


async def _get(app, url: str):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(url)


async def _post_project(app, mode: str):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/projects", json={"topic": "honey", "visual_mode": mode})


@pytest.fixture
def hosted_images(monkeypatch):
    """A deployment that *can* run fast_hybrid.

    Without this the mode is unavailable for an entirely different reason
    and every assertion below would pass for the wrong one — the failure
    mode this whole file exists to keep apart.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "replicate_api_token", "r8_test")
    assert visual_engine.unavailable_reason(VisualMode.FAST_HYBRID, get_settings()) is None


# --- the policy ---------------------------------------------------------


def test_only_stock_media_is_free():
    """Named explicitly rather than derived from the cost table: the two
    happen to agree today, and a cheaper generated mode later must not
    quietly become free."""
    assert credits.FREE_TIER_MODES == frozenset({VisualMode.STOCK_MEDIA})
    assert VisualMode.FAST_HYBRID not in credits.FREE_TIER_MODES
    assert VisualMode.AI_VIDEO not in credits.FREE_TIER_MODES


# --- what the picker shows ----------------------------------------------


async def test_an_unpaid_account_is_told_how_to_unlock_fast_hybrid(hosted_images):
    app = _app(visual_modes_route.router, pool=FakePool(purchased=False), user_id=USER)
    modes = {m["mode"]: m for m in (await _get(app, "/api/visual-modes")).json()}

    assert modes["stock_media"]["available"] is True
    assert modes["fast_hybrid"]["available"] is False
    assert "credit pack" in modes["fast_hybrid"]["reason"]


async def test_a_paying_account_gets_fast_hybrid_back(hosted_images):
    app = _app(visual_modes_route.router, pool=FakePool(purchased=True), user_id=USER)
    modes = {m["mode"]: m for m in (await _get(app, "/api/visual-modes")).json()}

    assert modes["fast_hybrid"]["available"] is True
    assert modes["fast_hybrid"]["reason"] is None


async def test_an_install_that_cannot_render_it_says_so_instead(monkeypatch):
    """The operator-facing reason outranks the upsell.

    Telling someone to buy credits for a mode this machine has no
    implementation of would be selling something the purchase cannot
    deliver — the exact failure the availability check was added to stop.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "replicate_api_token", None)
    monkeypatch.setattr(
        visual_engine.importlib.util,
        "find_spec",
        lambda name: None if name in ("torch", "diffusers") else object(),
    )

    app = _app(visual_modes_route.router, pool=FakePool(purchased=False), user_id=USER)
    modes = {m["mode"]: m for m in (await _get(app, "/api/visual-modes")).json()}

    assert modes["fast_hybrid"]["available"] is False
    assert "REPLICATE_API_TOKEN" in modes["fast_hybrid"]["reason"]
    assert "credit pack" not in modes["fast_hybrid"]["reason"]


async def test_ai_video_keeps_its_own_reason_even_unpaid(hosted_images, monkeypatch):
    """No credit pack unlocks it on this service, so none may be implied.

    The absence of torch is stated rather than assumed: a developer
    machine with diffusers installed *can* run ai_video, and there the
    upsell is the right answer — this asserts the hosted shape, which is
    the one with a customer reading the tooltip.
    """
    monkeypatch.setattr(
        visual_engine.importlib.util,
        "find_spec",
        lambda name: None if name in ("torch", "diffusers") else object(),
    )

    app = _app(visual_modes_route.router, pool=FakePool(purchased=False), user_id=USER)
    modes = {m["mode"]: m for m in (await _get(app, "/api/visual-modes")).json()}

    assert modes["ai_video"]["available"] is False
    assert "GPU" in modes["ai_video"]["reason"]
    assert "credit pack" not in modes["ai_video"]["reason"]


async def test_the_gate_asks_the_ledger_once(hosted_images):
    """Three modes, one question — it is about the account, not the mode."""
    pool = FakePool(purchased=False)
    app = _app(visual_modes_route.router, pool=pool, user_id=USER)
    await _get(app, "/api/visual-modes")

    assert len(pool.purchase_checks) == 1


async def test_self_hosting_is_never_gated(hosted_images):
    """No ledger and no user means no billing at all — a self-hoster
    supplying their own Replicate token must not be asked to buy ours."""
    app = _app(visual_modes_route.router, pool=None, user_id=None)
    modes = {m["mode"]: m for m in (await _get(app, "/api/visual-modes")).json()}

    assert modes["fast_hybrid"]["available"] is True


# --- what the API accepts -----------------------------------------------


async def test_creating_a_paid_mode_project_without_a_purchase_is_refused(hosted_images):
    app = _app(projects_route.router, pool=FakePool(purchased=False), user_id=USER)
    response = await _post_project(app, "fast_hybrid")

    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["error"] == "purchase_required"
    # The caller is told what it can have instead, so the UI can fall back
    # rather than dead-end.
    assert detail["available"] == ["stock_media"]


async def test_a_refused_render_is_never_queued(hosted_images):
    app = _app(projects_route.router, pool=FakePool(purchased=False), user_id=USER)
    await _post_project(app, "fast_hybrid")

    assert app.state.render_queue.submitted == []


async def test_stock_media_still_works_on_the_free_grant(hosted_images):
    """The grant has to buy something, or it isn't a trial.

    Goes through the real project store and the real charge path — only
    Postgres is stubbed — so this fails if the gate is ever widened to
    cover the one mode it must not.
    """
    app = _app(projects_route.router, pool=FakePool(purchased=False), user_id=USER)
    response = await _post_project(app, "stock_media")

    assert response.status_code == 201
    assert len(app.state.render_queue.submitted) == 1
