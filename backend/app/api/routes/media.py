"""My files: upload once, use in any number of projects.

The listing, upload and delete calls carry the user's bearer token like
every other call. Playing a file cannot — a <video> tag sends no header —
so, as for a finished project, an owner-checked call mints a short-lived
signed URL and the stream route accepts only that signature.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import current_user_id
from app.core.config import get_settings, media_root
from app.engines import render_engine
from app.services import beat_edits, media_store, uploads
from app.services.media_tokens import InvalidMediaToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])

_VIDEO_CAP = uploads.MAX_UPLOAD_BYTES
_AUDIO_CAP = beat_edits.MAX_MUSIC_BYTES


class MediaOut(BaseModel):
    id: str
    kind: str
    name: str
    size_bytes: int
    duration_s: float | None
    width: int | None
    height: int | None
    created_at: datetime


class MediaList(BaseModel):
    files: list[MediaOut]
    used_bytes: int
    quota_bytes: int


class MediaUrls(BaseModel):
    url: str
    poster_url: str | None
    expires_at: int


def _out(media: media_store.MediaFile) -> MediaOut:
    return MediaOut(
        id=media.id,
        kind=media.kind,
        name=media.name,
        size_bytes=media.size_bytes,
        duration_s=media.duration_s,
        width=media.width,
        height=media.height,
        created_at=media.created_at,
    )


def _quota_bytes() -> int:
    return get_settings().media_quota_mb * 1024 * 1024


def _token_subject(media_id: str) -> str:
    # Never a project id — those are bare UUIDs — so a token minted for a
    # file cannot be replayed against a project's download, or back.
    return f"media-{media_id}"


async def _chunks(file: UploadFile):
    while chunk := await file.read(1 << 20):
        yield chunk


def kind_of(filename: str, content_type: str | None) -> str | None:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in media_store.VIDEO_EXTS or (content_type or "").startswith("video/"):
        return "video"
    if ext in media_store.AUDIO_EXTS or (content_type or "").startswith("audio/"):
        return "audio"
    return None


async def describe(media: media_store.MediaFile) -> None:
    """Fill in what a probe can say about a file already on disk, and
    write its poster. Raises UploadRejected for something unreadable."""
    settings = get_settings()
    if media.kind == "video":
        probed = await uploads.probe(media.path, settings.ffprobe_binary)
        media.duration_s = round(probed.duration_s, 2)
        media.width, media.height = probed.width, probed.height
        await render_engine.extract_poster(
            media.path,
            media.poster,
            at_s=min(1.0, max(0.0, probed.duration_s / 2)),
            ffmpeg_binary=settings.ffmpeg_binary,
            ffprobe_binary=settings.ffprobe_binary,
        )
    else:
        media.duration_s = round(
            await beat_edits.probe_audio(media.path, settings.ffprobe_binary), 2
        )


async def keep(
    source_path, name: str, kind: str, user_id: str | None
) -> media_store.MediaFile | None:
    """Keep a file a project already has in My files, if it fits the quota.

    Best-effort by design: it runs after an upload has been accepted, and
    a full shelf is no reason to refuse the render the user asked for.
    """
    size = source_path.stat().st_size
    if await media_store.used_bytes(user_id) + size > _quota_bytes():
        logger.info("Not keeping %s for %s: over quota", name, user_id)
        return None
    media = media_store.MediaFile(
        id=media_store.new_id(),
        user_id=user_id,
        kind=kind,
        name=name[:200] or "file",
        ext=media_store.safe_ext(name, kind),
        size_bytes=size,
    )
    try:
        media_store.adopt(source_path, media)
        await describe(media)
        await media_store.add(media)
    except Exception:  # noqa: BLE001 - keeping a copy must never fail the upload
        logger.exception("Could not keep %s in My files", name)
        media_store.remove_files(media)
        return None
    return media


@router.get("", response_model=MediaList)
async def list_media(user_id: str | None = Depends(current_user_id)) -> MediaList:
    files = await media_store.list_for(user_id)
    return MediaList(
        files=[_out(m) for m in files],
        used_bytes=sum(m.size_bytes for m in files),
        quota_bytes=_quota_bytes(),
    )


@router.post("", response_model=MediaOut, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user_id),
) -> MediaOut:
    name = file.filename or "file"
    kind = kind_of(name, file.content_type)
    if kind is None:
        raise HTTPException(status_code=422, detail="Only video and audio files can be kept here.")

    media = media_store.MediaFile(
        id=media_store.new_id(),
        user_id=user_id,
        kind=kind,
        name=name[:200],
        ext=media_store.safe_ext(name, kind),
        size_bytes=0,
    )
    media_root()  # make sure the directory exists
    used = await media_store.used_bytes(user_id)
    cap = min(_VIDEO_CAP if kind == "video" else _AUDIO_CAP, max(0, _quota_bytes() - used))
    if cap <= 0:
        raise HTTPException(status_code=422, detail="Your files are full. Delete some to make room.")
    try:
        media.size_bytes = await uploads.save_stream(_chunks(file), media.path, cap)
        await describe(media)
    except uploads.UploadRejected as exc:
        media_store.remove_files(media)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        media_store.remove_files(media)
        raise
    await media_store.add(media)
    return _out(media)


@router.delete("/{media_id}", status_code=204)
async def delete_media(media_id: str, user_id: str | None = Depends(current_user_id)) -> None:
    media = await media_store.get_owned(media_id, user_id)
    if media is None:
        raise HTTPException(status_code=404, detail="No such file.")
    await media_store.delete(media)


@router.get("/{media_id}/url", response_model=MediaUrls)
async def media_urls(
    media_id: str, request: Request, user_id: str | None = Depends(current_user_id)
) -> MediaUrls:
    media = await media_store.get_owned(media_id, user_id)
    if media is None:
        raise HTTPException(status_code=404, detail="No such file.")
    token, expires_at = request.app.state.media_signer.sign(_token_subject(media_id))
    return MediaUrls(
        url=f"/api/media/{media_id}/stream?token={token}",
        poster_url=f"/api/media/{media_id}/poster?token={token}" if media.kind == "video" else None,
        expires_at=expires_at,
    )


async def _signed(media_id: str, token: str, request: Request) -> media_store.MediaFile:
    try:
        request.app.state.media_signer.verify(_token_subject(media_id), token)
    except InvalidMediaToken as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    media = await media_store._store.get(media_id)
    if media is None or not media.path.is_file():
        raise HTTPException(status_code=404, detail="No such file.")
    return media


@router.get("/{media_id}/stream")
async def stream_media(media_id: str, request: Request, token: str = Query(...)) -> FileResponse:
    media = await _signed(media_id, token, request)
    media_type = "video/mp4" if media.kind == "video" else "audio/mpeg"
    return FileResponse(media.path, media_type=media_type)


@router.get("/{media_id}/poster")
async def media_poster(media_id: str, request: Request, token: str = Query(...)) -> FileResponse:
    media = await _signed(media_id, token, request)
    if not media.poster.is_file():
        raise HTTPException(status_code=404, detail="No poster for this file.")
    return FileResponse(
        media.poster, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"}
    )
