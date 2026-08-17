"""Which visual modes this install can actually run.

Served for the same reason the art-style catalog is: the picker must not
offer something the renderer can't deliver. Here it matters more, because
the modes are priced differently and the pipeline hides its own failure —
generation that can't run falls back to stock footage rather than losing
the render, so a mode this machine cannot do still produces a video, just
not the one that was paid for.

The unavailable modes are listed rather than omitted, with the reason, so
a self-hoster can see that `fast_hybrid` needs a dependency they haven't
installed instead of wondering where the option went.

Two questions share this endpoint because the picker only has one place to
put the answer: what this *install* can render, and what this *account*
has paid to render. They are kept separate everywhere else — see
credits.FREE_TIER_MODES — and joined only here, at the point where a
tooltip has to say a single sentence to one person.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import billing_enabled, current_user_id, db_pool
from app.core.config import get_settings
from app.engines import visual_engine
from app.schemas.project import VisualMode
from app.services import credits

router = APIRouter(prefix="/api/visual-modes", tags=["visual-modes"])


class VisualModeOut(BaseModel):
    mode: VisualMode
    available: bool
    # Populated only when unavailable. Phrased for whoever runs the
    # install, since they are the only one who can change it.
    reason: str | None = None


@router.get("", response_model=list[VisualModeOut])
async def list_visual_modes(
    request: Request,
    user_id: str | None = Depends(current_user_id),
) -> list[VisualModeOut]:
    settings = get_settings()

    # Asked once, not once per mode: the answer is about the account, not
    # about any particular mode. On a self-hosted install there is no
    # ledger and no user, so nothing is gated and this never runs.
    pool = db_pool(request)
    gated = billing_enabled(pool, user_id) and not await credits.may_render_paid_mode(
        pool, user_id
    )

    out: list[VisualModeOut] = []
    for mode in VisualMode:
        reason = visual_engine.unavailable_reason(mode, settings)
        # Only ever a fallback. A mode this deployment cannot run at all
        # must keep saying so — telling someone to buy credits for
        # ai_video would be selling them something no purchase unlocks.
        if reason is None and gated and mode not in credits.FREE_TIER_MODES:
            reason = credits.PURCHASE_REQUIRED_REASON
        out.append(VisualModeOut(mode=mode, available=reason is None, reason=reason))
    return out
