"""What is trending, per region, for the studio's trends section."""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
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


# A trend's example videos, served from here rather than linked from
# YouTube: the page's CSP keeps images to this origin, and a visitor's
# browser asking Google for them would hand it their address for every
# card. Only an 11-character video id goes in, into a fixed URL, so this
# fetches YouTube's thumbnails and nothing else.
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_THUMBS: OrderedDict[str, bytes] = OrderedDict()
_THUMBS_KEPT = 400  # about 15 kB each


async def _fetch_thumbnail(video_id: str) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            got = await client.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg")
    except httpx.HTTPError:
        raise HTTPException(status_code=502) from None
    if got.status_code != 200 or not got.headers.get("content-type", "").startswith("image/"):
        raise HTTPException(status_code=404)
    return got.content


@router.get("/thumb/{video_id}")
async def thumbnail(video_id: str = Path(min_length=11, max_length=11)) -> Response:
    if not _VIDEO_ID.match(video_id):
        raise HTTPException(status_code=404)
    image = _THUMBS.get(video_id)
    if image is None:
        image = await _fetch_thumbnail(video_id)
        _THUMBS[video_id] = image
        while len(_THUMBS) > _THUMBS_KEPT:
            _THUMBS.popitem(last=False)
    else:
        _THUMBS.move_to_end(video_id)
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
