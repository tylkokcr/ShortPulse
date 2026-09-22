"""Selling credit packs through Stripe Checkout.

Two rules shape everything here, and both are about not trusting the
client:

  * **What was bought is decided server-side.** The browser sends a pack
    id and nothing else. Price and credit count are looked up from
    `credits.CREDIT_PACKS`, never read from the request — otherwise the
    checkout is a form where the customer types their own price.

  * **Credits are granted from the webhook, not from the redirect.** The
    success URL is a page the customer's browser is sent to, so anyone can
    visit it; the webhook is a signed message from Stripe. Granting on
    redirect is the classic way to give away a product for free.

The signature check is therefore load-bearing rather than ceremonial: this
handler adds credits, so an unverified webhook route is an endpoint that
mints them for whoever finds the URL.
"""

from __future__ import annotations

import logging

import stripe

from app.services.credits import CreditPack, pack_by_id

logger = logging.getLogger(__name__)


class PaymentsUnavailable(RuntimeError):
    """No Stripe key is configured — this install doesn't sell anything."""


class InvalidWebhook(ValueError):
    """The payload didn't come from Stripe, or didn't survive the trip."""


def enabled(settings) -> bool:
    return bool(settings.stripe_secret_key)


def _client(settings) -> stripe.StripeClient:
    if not enabled(settings):
        raise PaymentsUnavailable("No Stripe secret key is configured")
    return stripe.StripeClient(settings.stripe_secret_key)


async def create_checkout_session(
    settings, pack_id: str, user_id: str, email: str | None = None
) -> str:
    """Start a purchase and return the URL to send the customer to.

    `user_id` is carried in the session's metadata rather than in the
    return URL, because the return URL is under the customer's control
    once they are looking at it and the metadata comes back to us signed.
    """
    pack: CreditPack | None = pack_by_id(pack_id)
    if pack is None:
        raise ValueError(f"No such credit pack: {pack_id}")

    automatic_tax = bool(getattr(settings, "stripe_automatic_tax", False))

    # stripe types `params` as a TypedDict, which can only be satisfied by a
    # dict literal. The conditional spreads below — tax fields that exist
    # only when Stripe Tax is on — make this one a plain dict as far as the
    # checker is concerned. Narrow ignore so a stripe release that relaxes
    # the annotation shows up as an unused one rather than staying hidden.
    session = _client(settings).checkout.sessions.create(
        params={  # type: ignore[arg-type]
            "mode": "payment",
            "success_url": settings.checkout_success_url,
            "cancel_url": settings.checkout_cancel_url,
            "client_reference_id": user_id,
            **({"customer_email": email} if email else {}),
            "line_items": [
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": settings.stripe_currency,
                        "unit_amount": pack.price_cents,
                        # Inclusive: the price on the page is the price
                        # paid, and VAT is carved out of it. Exclusive
                        # would add tax at the last step, which for a
                        # consumer sale is the thing EU price-indication
                        # rules exist to prevent.
                        **({"tax_behavior": "inclusive"} if automatic_tax else {}),
                        "product_data": {
                            "name": f"{pack.credits} ShortPulse credits",
                            "description": (
                                "One-off purchase. Credits never expire and there is "
                                "no subscription."
                            ),
                        },
                    },
                }
            ],
            # Read back in the webhook. The pack id rather than the credit
            # count, so the amount granted is always resolved from the
            # server's own table even if this metadata is somehow stale.
            "metadata": {"pack_id": pack.id, "user_id": user_id},
            **(
                {
                    "automatic_tax": {"enabled": True},
                    # Stripe Tax needs to know where the buyer is. "auto"
                    # asks only where it cannot already tell.
                    "billing_address_collection": "auto",
                }
                if automatic_tax
                else {}
            ),
        }
    )
    if not session.url:
        raise PaymentsUnavailable("Stripe returned a session with no URL")
    return session.url


def parse_webhook(settings, payload: bytes, signature: str | None) -> stripe.Event:
    """Verify a webhook came from Stripe, and return the event.

    Refuses outright when no webhook secret is configured. An unsigned
    payload is indistinguishable from one an attacker wrote, and this
    event grants credits.
    """
    if not settings.stripe_webhook_secret:
        raise InvalidWebhook("No webhook secret is configured; refusing to trust the payload")
    if not signature:
        raise InvalidWebhook("Missing Stripe-Signature header")

    try:
        return stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise InvalidWebhook(str(exc)) from exc


def _field(obj, key: str, default=None):
    """Read a key from either a plain dict or a StripeObject.

    `StripeObject` is not a dict subclass and has no `.get` — calling one
    raises AttributeError, which is what a real webhook did on the first
    delivery while unit tests built from plain dicts passed happily.
    """
    try:
        return obj[key]
    except (KeyError, TypeError):
        return default


def purchase_from_event(event: stripe.Event) -> tuple[str, CreditPack, str] | None:
    """The (user_id, pack, idempotency_key) a completed checkout implies.

    Returns None for every other event type, and for a session that
    completed without being paid — Stripe emits
    `checkout.session.completed` for asynchronous methods before the money
    has actually arrived, so `payment_status` is what decides, not the
    event name.
    """
    if _field(event, "type") != "checkout.session.completed":
        return None

    session = _field(_field(event, "data", {}), "object")
    if session is None:
        return None
    session_id = _field(session, "id")

    if _field(session, "payment_status") != "paid":
        logger.info(
            "Checkout session %s completed but is not paid (%s); no credits granted",
            session_id,
            _field(session, "payment_status"),
        )
        return None

    metadata = _field(session, "metadata") or {}
    user_id = _field(metadata, "user_id") or _field(session, "client_reference_id")
    pack = pack_by_id(_field(metadata, "pack_id") or "")
    if not user_id or pack is None:
        logger.error(
            "Paid checkout session %s carries no usable user/pack metadata: %r",
            session_id,
            metadata,
        )
        return None

    # Keyed on the session, not the event: Stripe retries deliver a new
    # event id for the same purchase, and the ledger's uniqueness check is
    # what stops a retry from paying out twice.
    return user_id, pack, f"stripe:{session_id}"
