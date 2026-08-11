"""The art-style catalog.

Served rather than duplicated in the frontend so the picker can't offer a
look the renderer doesn't implement. The sample images live in
`frontend/public/art-styles/` and were each produced by this pipeline, with
the default checkpoint and settings, from the same subject prompt — the
point of showing them is that they are what you actually get.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import art_styles

router = APIRouter(prefix="/api/art-styles", tags=["art-styles"])


class ArtStyleOut(BaseModel):
    id: str
    name: str
    description: str
    sample: str
    is_default: bool


@router.get("", response_model=list[ArtStyleOut])
async def list_art_styles() -> list[ArtStyleOut]:
    return [
        ArtStyleOut(
            id=style.id,
            name=style.name,
            description=style.description,
            sample=style.sample,
            is_default=style.id == art_styles.DEFAULT_ART_STYLE.id,
        )
        for style in art_styles.ART_STYLES
    ]
