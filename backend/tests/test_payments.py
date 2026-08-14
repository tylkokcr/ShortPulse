"""Buying credits.

This is the one place in the product where money maps to something the
user receives, so what is pinned here is mostly what must *not* happen:
credits granted without a verified payment, granted twice for one
purchase, or granted in an amount the buyer chose.
"""

from __future__ import annotations

import json
import time

import pytest
import stripe

from app.services import credits as credits_module
from app.services import payments
from app.services.credits import pack_by_id


class Settings:
    def __init__(self, secret="sk_test_x", webhook_secret="whsec_test", automatic_tax=False):
        self.stripe_secret_key = secret
        self.stripe_webhook_secret = webhook_secret
        self.checkout_success_url = "https://app.test/ok"
        self.checkout_cancel_url = "https://app.test/no"
        self.stripe_currency = "usd"
        self.stripe_automatic_tax = automatic_tax


def _signed(payload: dict, secret: str = "whsec_test") -> tuple[bytes, str]:
    """A payload signed the way Stripe signs one."""
    body = json.dumps(payload).encode()
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(
        f"{timestamp}.{body.decode()}", secret
    )
    return body, f"t={timestamp},v1={signature}"


def _completed_session(**overrides) -> dict:
    session = {
        "id": "cs_test_123",
        "payment_status": "paid",
        "client_reference_id": "user-1",
        "metadata": {"pack_id": "creator", "user_id": "user-1"},
    }
    session.update(overrides)
    return {"type": "checkout.session.completed", "data": {"object": session}}


# --------------------------------------------------------------------------
# Webhook verification — the handler grants credits, so this is the door
# --------------------------------------------------------------------------


def test_an_unsigned_payload_is_refused():
    """Anyone can POST to a webhook URL. Without the signature check this
    endpoint mints credits for whoever finds it."""
    with pytest.raises(payments.InvalidWebhook, match="Missing Stripe-Signature"):
        payments.parse_webhook(Settings(), json.dumps(_completed_session()).encode(), None)


def test_a_payload_signed_with_the_wrong_secret_is_refused():
    body, signature = _signed(_completed_session(), secret="whsec_attacker")

    with pytest.raises(payments.InvalidWebhook):
        payments.parse_webhook(Settings(), body, signature)


def test_a_tampered_payload_is_refused():
    """The amount is not in the payload we trust, but the user id is —
    re-pointing a real purchase at another account must not verify."""
    body, signature = _signed(_completed_session())
    tampered = body.replace(b"user-1", b"user-2")

    with pytest.raises(payments.InvalidWebhook):
        payments.parse_webhook(Settings(), tampered, signature)


def test_a_correctly_signed_payload_is_accepted():
    body, signature = _signed(_completed_session())

    event = payments.parse_webhook(Settings(), body, signature)

    assert event["type"] == "checkout.session.completed"


def test_verification_is_refused_outright_with_no_secret_configured():
    """Rather than falling back to trusting the payload — a deployment that
    forgot the secret would otherwise be wide open and look fine."""
    body, signature = _signed(_completed_session())

    with pytest.raises(payments.InvalidWebhook, match="No webhook secret"):
        payments.parse_webhook(Settings(webhook_secret=None), body, signature)


# --------------------------------------------------------------------------
# What a verified event is worth
# --------------------------------------------------------------------------


def test_a_paid_session_resolves_to_the_pack_the_server_knows():
    user_id, pack, key = payments.purchase_from_event(_completed_session())

    assert user_id == "user-1"
    assert pack is pack_by_id("creator")
    assert pack.credits == 400


def test_an_unpaid_session_grants_nothing():
    """Stripe fires checkout.session.completed for asynchronous payment
    methods before the money arrives. Granting on the event name alone
    hands out credits for a payment that may still fail."""
    assert payments.purchase_from_event(_completed_session(payment_status="unpaid")) is None


def test_other_event_types_are_ignored():
    assert payments.purchase_from_event({"type": "payment_intent.created", "data": {}}) is None


def test_an_unknown_pack_id_grants_nothing():
    """Metadata could name a pack that has since been removed. Better to
    grant nothing and have someone look than to guess an amount."""
    event = _completed_session(metadata={"pack_id": "legendary", "user_id": "user-1"})

    assert payments.purchase_from_event(event) is None


def test_the_idempotency_key_is_the_session_not_the_event():
    """Stripe retries a webhook until it gets a 2xx, and each delivery
    carries a new event id. Keying on the event would pay out again on
    every retry."""
    first = payments.purchase_from_event(_completed_session())
    retry = payments.purchase_from_event(_completed_session())

    assert first[2] == retry[2] == "stripe:cs_test_123"


def test_a_different_purchase_gets_a_different_key():
    other = payments.purchase_from_event(_completed_session(id="cs_test_456"))

    assert other[2] == "stripe:cs_test_456"


# --------------------------------------------------------------------------
# Checkout — the price is not the client's to choose
# --------------------------------------------------------------------------


async def test_the_amount_charged_comes_from_the_server_table(monkeypatch):
    captured = {}

    class FakeSessions:
        def create(self, params):
            captured.update(params)
            return type("S", (), {"url": "https://checkout.stripe.test/s"})()

    class FakeClient:
        checkout = type("C", (), {"sessions": FakeSessions()})()

    monkeypatch.setattr(payments, "_client", lambda settings: FakeClient())

    url = await payments.create_checkout_session(Settings(), "starter", "user-1")

    assert url == "https://checkout.stripe.test/s"
    line = captured["line_items"][0]["price_data"]
    assert line["unit_amount"] == pack_by_id("starter").price_cents
    # The buyer is identified in signed metadata, not in the return URL.
    assert captured["metadata"] == {"pack_id": "starter", "user_id": "user-1"}
    assert captured["client_reference_id"] == "user-1"


async def test_an_unknown_pack_cannot_be_bought():
    with pytest.raises(ValueError, match="No such credit pack"):
        await payments.create_checkout_session(Settings(), "free-money", "user-1")


async def test_checkout_is_unavailable_without_a_key():
    with pytest.raises(payments.PaymentsUnavailable):
        await payments.create_checkout_session(Settings(secret=None), "starter", "user-1")


# --------------------------------------------------------------------------
# The routes — that the wiring actually calls the checks above
# --------------------------------------------------------------------------


@pytest.fixture
def api(monkeypatch):
    from fastapi import FastAPI

    from app.api.routes import credits as credits_route
    from app.core import config as core_config

    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")

    app = FastAPI()
    app.include_router(credits_route.router)
    app.state.db_pool = None
    return app


def _client(app):
    import httpx

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_the_webhook_route_rejects_an_unsigned_post(api):
    """The route must not be reachable without a signature — this is the
    endpoint that adds credits."""
    async with _client(api) as client:
        response = await client.post("/api/credits/webhook", json=_completed_session())

    assert response.status_code == 400


async def test_the_webhook_route_rejects_a_forged_signature(api):
    body, _ = _signed(_completed_session())
    async with _client(api) as client:
        response = await client.post(
            "/api/credits/webhook",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )

    assert response.status_code == 400


async def test_a_verified_webhook_with_no_ledger_does_not_pretend_to_succeed(api):
    """Returning 200 here would tell Stripe the purchase was honoured and
    stop it retrying, losing the grant silently."""
    body, signature = _signed(_completed_session())
    async with _client(api) as client:
        response = await client.post(
            "/api/credits/webhook", content=body, headers={"Stripe-Signature": signature}
        )

    assert response.status_code == 503


async def test_the_webhook_survives_require_auth(monkeypatch):
    """The production configuration, which is the only one that broke.

    Stripe authenticates by signature, not by bearer token, so with
    REQUIRE_AUTH on the auth middleware answered its callback 401 before
    the handler ran. Every purchase would have been charged and never
    credited, and nothing would have logged an error — from the API's side
    a 401 is a perfectly ordinary answer.

    Asserting only that the webhook is not 401 would pass with the gate
    switched off entirely, so this checks both doors in the same app: the
    webhook reaches its handler (503 — no ledger configured here) while an
    ordinary route is still refused.
    """
    from fastapi import FastAPI

    from app.api.middleware import SupabaseAuthMiddleware
    from app.api.routes import credits as credits_route
    from app.core import config as core_config

    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")

    app = FastAPI()
    app.include_router(credits_route.router)
    app.add_middleware(SupabaseAuthMiddleware, verifier=None, require_auth=True)
    app.state.db_pool = None

    body, signature = _signed(_completed_session())
    async with _client(app) as client:
        hook = await client.post(
            "/api/credits/webhook", content=body, headers={"Stripe-Signature": signature}
        )
        ordinary = await client.get("/api/credits")

    assert ordinary.status_code == 401, "require_auth is not actually on; test proves nothing"
    assert hook.status_code != 401, "Stripe was refused — purchases would never be credited"
    assert hook.status_code == 503


async def test_a_visitor_is_quoted_the_currency_the_deployment_charges(monkeypatch):
    """What the landing page shows has to be what checkout takes.

    The pricing section is rendered for people who are not signed in. On
    a deployment with REQUIRE_AUTH its call was refused, the failure was
    caught, and it drew its hardcoded fallback — US dollars, no VAT —
    while the checkout it linked to charged euros including VAT.
    """
    from fastapi import FastAPI

    from app.api.middleware import SupabaseAuthMiddleware
    from app.api.routes import credits as credits_route
    from app.core import config as core_config

    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "stripe_currency", "eur")
    monkeypatch.setattr(settings, "stripe_automatic_tax", True)

    app = FastAPI()
    app.include_router(credits_route.router)
    app.add_middleware(SupabaseAuthMiddleware, verifier=None, require_auth=True)
    app.state.db_pool = None

    async with _client(app) as client:
        public = await client.get("/api/credits/packs")
        private = await client.get("/api/credits")

    assert private.status_code == 401, "require_auth is not actually on; test proves nothing"
    assert public.status_code == 200
    body = public.json()
    assert body["currency"] == "eur"
    assert body["tax_included"] is True
    assert [p["id"] for p in body["packs"]] == [p.id for p in credits_module.CREDIT_PACKS]
    # The shop window holds no private data.
    assert "balance" not in body and "entries" not in body


async def test_the_price_list_says_whether_this_deployment_can_actually_sell(monkeypatch):
    """Accounts and payments are separate switches, and `sold` reports the
    combination — nothing else does.

    A deployment can have a ledger and signed-in users and no Stripe key at
    all, which is the shape of a launch that is not taking money yet.
    `CreditSummary.enabled` is true there, so the UI cannot read that to
    decide whether to offer a purchase: it would draw three priced packs
    whose only possible answer is 503, after the buyer had already agreed
    to give up their right of withdrawal.

    The packs stay in the response either way. The tariff is also what
    tells a self-hoster what a credit is worth, and that is true of an
    install that sells nothing.
    """
    from fastapi import FastAPI

    from app.api.routes import credits as credits_route
    from app.core import config as core_config

    settings = core_config.get_settings()

    app = FastAPI()
    app.include_router(credits_route.router)
    # `sold` only asks whether there is somewhere to record credits, so
    # anything that is not None stands in for a pool.
    app.state.db_pool = object()

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_live_x")
    async with _client(app) as client:
        charging = (await client.get("/api/credits/packs")).json()

    monkeypatch.setattr(settings, "stripe_secret_key", "")
    async with _client(app) as client:
        not_charging = (await client.get("/api/credits/packs")).json()

    assert charging["sold"] is True
    assert not_charging["sold"] is False, (
        "a deployment with no Stripe key advertised itself as able to sell"
    )
    assert not_charging["packs"] == charging["packs"]


async def test_an_unsigned_post_is_still_refused_under_require_auth(monkeypatch):
    """Exempting the path from authentication must not exempt it from the
    signature check — that would make it a free-credits endpoint."""
    from fastapi import FastAPI

    from app.api.middleware import SupabaseAuthMiddleware
    from app.api.routes import credits as credits_route
    from app.core import config as core_config

    settings = core_config.get_settings()
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")

    app = FastAPI()
    app.include_router(credits_route.router)
    app.add_middleware(SupabaseAuthMiddleware, verifier=None, require_auth=True)
    app.state.db_pool = None

    async with _client(app) as client:
        response = await client.post("/api/credits/webhook", json=_completed_session())

    assert response.status_code == 400


async def test_anonymous_callers_cannot_start_a_checkout(api):
    """Credits belong to an account, so there has to be one to credit."""
    async with _client(api) as client:
        response = await client.post("/api/credits/checkout", json={"pack_id": "starter"})

    assert response.status_code == 401


async def test_a_genuinely_parsed_stripe_event_is_readable():
    """The regression that the plain-dict tests above could not catch.

    `StripeObject` is not a dict subclass and has no `.get`, so code
    written against dicts raises AttributeError on the first real webhook
    while every unit test passes. This one goes through the actual parser.
    """
    body, signature = _signed(_completed_session())
    event = payments.parse_webhook(Settings(), body, signature)

    assert not isinstance(event["data"]["object"], dict)  # the trap

    user_id, pack, key = payments.purchase_from_event(event)

    assert (user_id, pack.credits, key) == ("user-1", 400, "stripe:cs_test_123")


# --------------------------------------------------------------------------
# VAT
#
# Selling digital services to EU consumers means tax at the buyer's local
# rate. What matters here is that turning it on doesn't quietly change what
# the customer is charged relative to the price they were shown.
# --------------------------------------------------------------------------


def _captured_session(monkeypatch, settings):
    captured = {}

    class FakeSessions:
        def create(self, params):
            captured.update(params)
            return type("S", (), {"url": "https://checkout.stripe.test/s"})()

    class FakeClient:
        checkout = type("C", (), {"sessions": FakeSessions()})()

    monkeypatch.setattr(payments, "_client", lambda s: FakeClient())
    return captured


async def test_tax_is_not_sent_unless_it_is_configured(monkeypatch):
    """`automatic_tax` fails the whole checkout unless Stripe Tax is
    activated with an origin address, so it must not be on by default."""
    captured = _captured_session(monkeypatch, Settings())

    await payments.create_checkout_session(Settings(), "starter", "user-1")

    assert "automatic_tax" not in captured
    assert "tax_behavior" not in captured["line_items"][0]["price_data"]


async def test_tax_is_carved_out_of_the_advertised_price(monkeypatch):
    """Inclusive, not exclusive: the page says $9, so $9 is what gets
    charged and the VAT comes out of it. Adding tax at the final step is
    what EU price-indication rules exist to stop."""
    settings = Settings(automatic_tax=True)
    captured = _captured_session(monkeypatch, settings)

    await payments.create_checkout_session(settings, "starter", "user-1")

    assert captured["automatic_tax"] == {"enabled": True}
    price = captured["line_items"][0]["price_data"]
    assert price["tax_behavior"] == "inclusive"
    assert price["unit_amount"] == pack_by_id("starter").price_cents


async def test_the_currency_is_a_deployment_setting(monkeypatch):
    settings = Settings()
    settings.stripe_currency = "eur"
    captured = _captured_session(monkeypatch, settings)

    await payments.create_checkout_session(settings, "starter", "user-1")

    assert captured["line_items"][0]["price_data"]["currency"] == "eur"
