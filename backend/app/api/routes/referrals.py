"""Invite links: an account's own code and its tally, and the call a
new account makes to say which link brought it. See services/referrals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import billing_for, current_user_id, db_pool
from app.services import referrals

router = APIRouter(prefix="/api/referrals", tags=["referrals"])


class ReferralSummary(BaseModel):
    code: str
    joined: int
    rewarded: int
    reward: int
    cap: int


class ClaimIn(BaseModel):
    code: str = Field(max_length=32)


class ClaimOut(BaseModel):
    claimed: bool


@router.get("", response_model=ReferralSummary)
async def get_referrals(
    request: Request, user_id: str | None = Depends(current_user_id)
) -> ReferralSummary:
    billing = billing_for(db_pool(request), user_id)
    if billing is None:
        raise HTTPException(status_code=404, detail="This install has no credits to give.")
    return ReferralSummary(**vars(await referrals.summary(billing.pool, billing.user_id)))


@router.post("/claim", response_model=ClaimOut)
async def claim_referral(
    body: ClaimIn, request: Request, user_id: str | None = Depends(current_user_id)
) -> ClaimOut:
    billing = billing_for(db_pool(request), user_id)
    if billing is None:
        return ClaimOut(claimed=False)
    # The same answer for every refusal: whether a code exists, or whose,
    # is nothing a caller needs to learn from this.
    claimed = await referrals.claim(billing.pool, billing.user_id, body.code.strip().lower())
    return ClaimOut(claimed=claimed)
