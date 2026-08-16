"""Voice catalog and audio previews.

The preview matters more than any description we could write: Piper's
catalog records no gender or tone, so "hear it" is the only honest way to
choose. Samples are synthesized once and cached on disk — the first one for
a given voice also downloads its model (tens of MB), which is why the UI
warns about that rather than looking hung.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.engines import audio_engine
from app.schemas.project import TTSProvider, VoiceConfig
from app.services import voices as voice_catalog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voices", tags=["voices"])

def _preview_dir() -> Path:
    """Where synthesized samples are cached.

    Beside the projects rather than inside the image: on a container
    deployment `storage_root` is the mounted volume, so previews survive a
    redeploy instead of every voice in the catalog being re-synthesized the
    first time someone opens the picker after one. Resolves to the same
    path as before on a local checkout.
    """
    return get_settings().storage_root.parent / "voice_previews"

# One synthesis at a time. Each loads a model into memory, and a page that
# renders a dozen voices could otherwise fire a dozen concurrent loads.
_preview_lock = asyncio.Lock()


class VoiceOut(BaseModel):
    id: str
    name: str
    language: str
    region: str
    quality: str
    is_default: bool


@router.get("", response_model=list[VoiceOut])
async def list_voices(
    language: str | None = Query(default=None, description="ISO code, e.g. 'tr'")
) -> list[VoiceOut]:
    catalog = (
        voice_catalog.for_language(language) if language else list(voice_catalog.VOICES)
    )
    return [
        VoiceOut(
            id=voice.id,
            name=voice.name,
            language=voice.language,
            region=voice.region,
            quality=voice.quality,
            is_default=voice.is_default,
        )
        for voice in catalog
    ]


@router.get("/preview")
async def preview(voice_id: str = Query(..., description="Voice id from GET /api/voices")):
    """A short spoken sample of one voice, as WAV."""
    voice = voice_catalog.by_id(voice_id)
    if voice is None:
        # Only catalog entries are synthesizable: `voice_id` reaches
        # huggingface_hub as a repo path, so accepting arbitrary strings
        # would let a caller probe for files in that repo.
        raise HTTPException(status_code=404, detail=f"Unknown voice: {voice_id!r}")

    preview_dir = _preview_dir()
    preview_dir.mkdir(parents=True, exist_ok=True)
    cached = preview_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', voice.id)}.wav"

    if not cached.exists():
        line = voice_catalog.PREVIEW_LINE.get(voice.language, voice_catalog.PREVIEW_LINE["en"])
        async with _preview_lock:
            # Re-check: another request may have produced it while we waited.
            if not cached.exists():
                try:
                    await audio_engine.synthesize_line(
                        line,
                        VoiceConfig(provider=TTSProvider.PIPER, voice_id=voice.id),
                        cached,
                        language=voice.language,
                    )
                except Exception as exc:  # noqa: BLE001 - surfaced to the client
                    logger.exception("Voice preview failed for %s", voice.id)
                    cached.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=502, detail=f"Could not synthesize preview: {exc}"
                    ) from exc

    return FileResponse(
        cached,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )
