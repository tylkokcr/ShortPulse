"""Credit balance and ledger history for the signed-in user.

`enabled: false` is the self-hosted answer — no database or no account
means renders are free and the UI should hide anything credit-related
rather than show a balance of zero and imply the user is broke.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import billing_enabled, current_user_id, db_pool
from app.core.config import get_settings
from app.schemas.project import ProjectConfig, VideoLength, VisualMode
from app.services import credits, payments

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credits", tags=["credits"])


class LedgerEntryOut(BaseModel):
    id: int
    delta: int
    reason: str
    project_id: str | None = None
    note: str | None = None
    created_at: datetime


class CreditPackOut(BaseModel):
    id: str
    credits: int
    price_cents: int
    popular: bool


class CreditSummary(BaseModel):
    enabled: bool
    # What the packs are priced in. Sent rather than assumed, so a
    # deployment can switch to EUR without the UI still drawing "$".
    currency: str = "usd"
    # Whether the displayed price already contains VAT. EU consumer sales
    # are inclusive; the UI says so rather than leaving the buyer to find
    # out at the last step.
    tax_included: bool = False
    balance: int = 0
    entries: list[LedgerEntryOut] = []
    # Cost of every render shape, so the UI can quote a price before the
    # user commits rather than after they've been charged.
    pricing: dict[str, int] = {}
    # Served even when billing is off, so the marketing page can render
    # real prices without a second endpoint or a hardcoded copy that
    # drifts from what the ledger actually charges.
    packs: list[CreditPackOut] = []


def _pricing_table() -> dict[str, int]:
    return {
        f"{mode.value}:{length.value}": credits.cost_for(
            ProjectConfig(topic="quote", visual_mode=mode, video_length=length)
        )
        for mode in VisualMode
        for length in VideoLength
    }


def _packs() -> list[CreditPackOut]:
    return [CreditPackOut(**vars(pack)) for pack in credits.CREDIT_PACKS]


@router.get("", response_model=CreditSummary)
async def get_credits(
    request: Request, user_id: str | None = Depends(current_user_id)
) -> CreditSummary:
    settings = get_settings()
    pool = db_pool(request)
    if not billing_enabled(pool, user_id):
        return CreditSummary(enabled=False, packs=_packs())

    return CreditSummary(
        enabled=True,
        currency=settings.stripe_currency,
        tax_included=settings.stripe_automatic_tax,
        balance=await credits.balance(pool, user_id),
        entries=[
            LedgerEntryOut(**vars(entry)) for entry in await credits.history(pool, user_id)
        ],
        pricing=_pricing_table(),
        packs=_packs(),
    )


class CheckoutRequest(BaseModel):
    pack_id: str


class CheckoutSession(BaseModel):
    url: str


@router.post("/checkout", response_model=CheckoutSession)
async def start_checkout(
    body: CheckoutRequest,
    request: Request,
    user_id: str | None = Depends(current_user_id),
) -> CheckoutSession:
    """Begin a credit-pack purchase.

    The request names a pack and nothing more. What it costs and what it
    is worth are looked up server-side — accepting either from the client
    would be a checkout where the customer sets their own price.
    """
    settings = get_settings()
    if not payments.enabled(settings):
        raise HTTPException(status_code=503, detail="This install doesn't sell credits.")
    if user_id is None:
        # Credits belong to an account, so there has to be one to credit.
        raise HTTPException(status_code=401, detail="Sign in to buy credits.")

    try:
        url = await payments.create_checkout_session(
            settings, body.pack_id, user_id, email=getattr(request.state, "user_email", None)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except payments.PaymentsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return CheckoutSession(url=url)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request) -> dict:
    """Grant credits for a completed purchase.

    This is the only place credits are added for money, deliberately: the
    success URL is a page the customer's browser is sent to and anyone can
    open it, while this arrives signed by Stripe. The signature check
    below is what stands between the ledger and a free-credits endpoint.
    """
    settings = get_settings()
    payload = await request.body()

    try:
        event = payments.parse_webhook(
            settings, payload, request.headers.get("Stripe-Signature")
        )
    except payments.InvalidWebhook as exc:
        logger.warning("Rejected a Stripe webhook: %s", exc)
        # 400, not 403: Stripe retries on 5xx and gives up on 4xx, and a
        # payload we cannot verify will never become verifiable.
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc

    purchase = payments.purchase_from_event(event)
    if purchase is None:
        return {"received": True}

    user_id, pack, idempotency_key = purchase
    pool = db_pool(request)
    if pool is None:
        logger.error("Paid checkout for %s arrived but there is no database to credit", user_id)
        raise HTTPException(status_code=503, detail="No ledger configured")

    balance = await credits.grant(
        pool,
        user_id,
        pack.credits,
        reason="purchase",
        # Stripe retries the same purchase until it gets a 2xx, so the
        # ledger's uniqueness constraint is what makes that safe.
        idempotency_key=idempotency_key,
        note=f"{pack.id} pack",
    )
    logger.info(
        "Granted %d credits to %s for %s (balance %d)", pack.credits, user_id, pack.id, balance
    )
    return {"received": True}
