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
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.engines import visual_engine
from app.schemas.project import VisualMode

router = APIRouter(prefix="/api/visual-modes", tags=["visual-modes"])


class VisualModeOut(BaseModel):
    mode: VisualMode
    available: bool
    # Populated only when unavailable. Phrased for whoever runs the
    # install, since they are the only one who can change it.
    reason: str | None = None


@router.get("", response_model=list[VisualModeOut])
async def list_visual_modes() -> list[VisualModeOut]:
    settings = get_settings()
    return [
        VisualModeOut(
            mode=mode,
            available=(reason := visual_engine.unavailable_reason(mode, settings)) is None,
            reason=reason,
        )
        for mode in VisualMode
    ]
