"""What is trending, per region, for the studio's trends section."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import current_user_id
from app.core.config import get_settings
from app.services import trends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trends", tags=["trends"])


class RegionsOut(BaseModel):
    enabled: bool
    regions: list[str]


class TrendsOut(BaseModel):
    region: str
    lang: str
    generated_at: datetime
    fetched_at: datetime
    summary: str
    trends: list[dict]
    songs: list[dict]


@router.get("/regions", response_model=RegionsOut)
async def regions() -> RegionsOut:
    return RegionsOut(enabled=bool(get_settings().youtube_api_key), regions=list(trends.REGIONS))


@router.get("", response_model=TrendsOut)
async def get_trends(
    region: str = Query("TR", min_length=2, max_length=2),
    lang: str = Query("en", min_length=2, max_length=2),
    user_id: str | None = Depends(current_user_id),
) -> TrendsOut:
    settings = get_settings()
    if not settings.youtube_api_key:
        raise HTTPException(status_code=404, detail="Trends are not set up here.")
    region, lang = region.upper(), lang.lower()
    # Both from fixed lists: each pair is an analysis the server writes and
    # keeps, so an open-ended value would be a way to make it write many.
    if region not in trends.REGIONS:
        raise HTTPException(status_code=422, detail="That region isn't offered.")
    if lang not in trends.LANGS:
        lang = "en"
    try:
        report = await trends.get_report(region, lang, settings)
    except Exception:  # noqa: BLE001 - a platform or the model failing is a 503, not a 500
        logger.exception("Trends for %s/%s failed", region, lang)
        report = None
    if report is None:
        raise HTTPException(status_code=503, detail="Trends couldn't be collected just now.")
    return TrendsOut(
        region=report.region,
        lang=report.lang,
        generated_at=report.generated_at,
        fetched_at=report.fetched_at,
        summary=report.report.get("summary", ""),
        trends=report.report.get("trends", []),
        songs=report.songs,
    )
