"""Credit balance and ledger history for the signed-in user.

`enabled: false` is the self-hosted answer — no database or no account
means renders are free and the UI should hide anything credit-related
rather than show a balance of zero and imply the user is broke.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import billing_enabled, current_user_id, db_pool
from app.schemas.project import ProjectConfig, VideoLength, VisualMode
from app.services import credits

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
    pool = db_pool(request)
    if not billing_enabled(pool, user_id):
        return CreditSummary(enabled=False, packs=_packs())

    return CreditSummary(
        enabled=True,
        balance=await credits.balance(pool, user_id),
        entries=[
            LedgerEntryOut(**vars(entry)) for entry in await credits.history(pool, user_id)
        ],
        pricing=_pricing_table(),
        packs=_packs(),
    )
