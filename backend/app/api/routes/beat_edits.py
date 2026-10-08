"""Cut the user's own clips to a track.

The footage and, when they bring one, the music are the user's — this
endpoint never searches for or fetches either. That is the line between a
tool for editing your own material and one that republishes other
people's: see engines/beat_edit.py.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.api.deps import billing_for, current_user_id, db_pool
from app.api.routes.media import keep as keep_in_files
from app.api.routes.music import track_path_for
from app.core.config import get_settings, project_dir
from app.schemas.project import (
    BeatEditSpec,
    BeatEditStyle,
    Project,
    ProjectConfig,
    ProjectSource,
)
from app.services import beat_edits, credits, media_store, project_store, uploads

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/beat-edits", tags=["beat-edits"])


async def _chunks(file: UploadFile):
    while chunk := await file.read(1 << 20):
        yield chunk


@router.post("", response_model=Project, status_code=201)
async def create_beat_edit(
    request: Request,
    clips: list[UploadFile] = File(default=[]),
    music: UploadFile | None = File(None),
    music_track_id: str = Form(""),
    # Instead of uploading: files already in My files (routes/media.py).
    # May be mixed with uploaded clips; the files come first.
    clip_media_ids: list[str] = Form(default=[]),
    music_media_id: str = Form(""),
    # Keep the uploaded clips and song in My files too.
    save_to_files: bool = Form(False),
    duration_s: float = Form(15.0),
    style: str = Form(BeatEditStyle.ENERGETIC.value),
    music_start_s: float | None = Form(None),
    title: str = Form(""),
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Accept the clips and a track, then queue the edit.

    The same order as an upload: an id first so the files have a
    server-chosen place to land, every file written and probed, the row
    created, the charge last — a rejected clip never costs a credit — and
    one unwind for all of it.
    """
    settings = get_settings()

    picked_clips = []
    for media_id in (m.strip() for m in clip_media_ids if m.strip()):
        media = await media_store.get_owned(media_id, user_id)
        if media is None or media.kind != "video":
            raise HTTPException(status_code=422, detail="One of those clips isn't in your files.")
        picked_clips.append(media)
    picked_music = None
    if music_media_id.strip():
        picked_music = await media_store.get_owned(music_media_id.strip(), user_id)
        if picked_music is None or picked_music.kind != "audio":
            raise HTTPException(status_code=422, detail="That song isn't in your files.")

    total_clips = len(clips) + len(picked_clips)
    if total_clips == 0:
        raise HTTPException(status_code=422, detail="Add at least one clip.")
    if total_clips > beat_edits.MAX_CLIPS:
        raise HTTPException(
            status_code=422,
            detail={"error": "too_many_clips", "max": beat_edits.MAX_CLIPS},
        )
    try:
        chosen_style = BeatEditStyle(style.strip())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"error": "unsupported_style", "supported": [s.value for s in BeatEditStyle]},
        ) from None

    track_id = music_track_id.strip() or None
    chosen = sum(x is not None for x in (music, track_id, picked_music))
    if chosen == 0:
        raise HTTPException(status_code=422, detail="Pick a track or upload your own.")
    if chosen > 1:
        raise HTTPException(status_code=422, detail="Pick one track, not several.")
    if track_id is not None:
        try:
            library_track = track_path_for(track_id)
        except HTTPException:
            raise HTTPException(status_code=422, detail="That track isn't in the library.") from None
        track_length = await beat_edits.probe_audio(library_track, settings.ffprobe_binary)
    else:
        track_length = 0.0

    project_id = str(uuid.uuid4())
    paths = project_dir(project_id)
    created = False
    try:
        total = 0
        for index, media in enumerate(picked_clips):
            media_store.link_into(media, beat_edits.clip_path(paths, index, media.ext))
        kept: list[tuple[Path, str, str]] = []
        for offset, clip in enumerate(clips):
            index = len(picked_clips) + offset
            suffix = Path(clip.filename or "").suffix.lower()
            destination = beat_edits.clip_path(paths, index, suffix)
            try:
                total += await uploads.save_stream(_chunks(clip), destination)
                await uploads.probe(destination, settings.ffprobe_binary)
            except uploads.UploadRejected as exc:
                raise HTTPException(
                    status_code=422, detail=f"{clip.filename or 'A clip'}: {exc}"
                ) from exc
            kept.append((destination, clip.filename or f"clip {index + 1}", "video"))
            if total > beat_edits.max_total_bytes():
                raise HTTPException(
                    status_code=422,
                    detail=f"Clips come to more than "
                    f"{beat_edits.max_total_bytes() // (1024 * 1024)}MB together.",
                )

        if picked_music is not None:
            destination = beat_edits.music_path(paths, picked_music.ext)
            media_store.link_into(picked_music, destination)
            track_length = await beat_edits.probe_audio(destination, settings.ffprobe_binary)
        elif music is not None:
            suffix = Path(music.filename or "").suffix.lower()
            destination = beat_edits.music_path(paths, suffix)
            try:
                await uploads.save_stream(_chunks(music), destination, beat_edits.MAX_MUSIC_BYTES)
                track_length = await beat_edits.probe_audio(destination, settings.ffprobe_binary)
            except uploads.UploadRejected as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            kept.append((destination, music.filename or "song", "audio"))

        if track_length < 5.0:
            raise HTTPException(status_code=422, detail="That track is too short to cut to.")

        spec = BeatEditSpec(
            clip_count=total_clips,
            music_track_id=track_id,
            music_uploaded=music is not None or picked_music is not None,
            # A video longer than the track would end in silence.
            duration_s=min(max(duration_s, 5.0), 60.0, track_length),
            style=chosen_style,
            music_start_s=music_start_s,
        )
        config = ProjectConfig(
            id=project_id,
            topic=title.strip() or "Beat edit",
            source=ProjectSource.BEAT_EDIT,
            beat_edit=spec,
            # Any clip from a YouTube link makes the whole edit one that is
            # never posted through our connections (services/link_import.py).
            source_origin="youtube" if any(m.origin == "youtube" for m in picked_clips) else None,
        )
        # The track is the soundtrack; nothing is mixed under it, and the
        # editor must not add the default one when it re-burns.
        config.music.enabled = False

        await project_store.create_project(config, user_id)
        created = True

        billing = billing_for(db_pool(request), user_id)
        if billing is not None:
            cost = credits.cost_for(config)
            try:
                await credits.spend(
                    billing.pool,
                    billing.user_id,
                    cost,
                    project_id=config.id,
                    idempotency_key=f"render:{config.id}",
                    note="beat_edit",
                )
            except credits.InsufficientCredits as exc:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "insufficient_credits",
                        "balance": exc.balance,
                        "required": exc.required,
                    },
                ) from exc
            project = await project_store.update_project(config.id, credits_cost=cost)
        else:
            project = await project_store.get_project(config.id)  # type: ignore[assignment]
    except Exception:
        if created:
            await project_store.delete_project(project_id)
        shutil.rmtree(paths, ignore_errors=True)
        raise

    assert project is not None
    if save_to_files:
        for path, name, kind in kept:
            await keep_in_files(path, name, kind, user_id)
    await request.app.state.render_queue.submit(project)
    return project


class TrackAnalysis(BaseModel):
    """What the panel draws under the song: its shape, where the bars fall,
    where it drops, and where an edit of each length would start."""

    duration_s: float
    tempo_bpm: float
    drop_s: float | None
    downbeats: list[float]
    envelope: list[float]
    suggested_starts: dict[str, float]


_LENGTHS = (10, 15, 30, 60)


def _analysis_of(path: Path, ffmpeg: str) -> TrackAnalysis:
    from app.engines import beat_edit

    grid = beat_edit.analyze_beats(path, ffmpeg)
    return TrackAnalysis(
        duration_s=round(grid.duration_s, 2),
        tempo_bpm=round(grid.tempo_bpm, 1),
        drop_s=round(grid.drop_s, 2) if grid.drop_s is not None else None,
        downbeats=[round(b, 3) for b in grid.downbeats],
        envelope=beat_edit.envelope(path, 240, ffmpeg),
        suggested_starts={
            str(length): round(beat_edit.default_start(grid, float(length)), 3) for length in _LENGTHS
        },
    )


@lru_cache(maxsize=64)
def _library_analysis(track_path: str, ffmpeg: str) -> TrackAnalysis:
    # The library does not change while the server runs, and the same few
    # tracks are picked over and over: a second of numpy per pick is a
    # second the panel waits for nothing.
    return _analysis_of(Path(track_path), ffmpeg)


@router.post("/analyze", response_model=TrackAnalysis)
async def analyze_track(
    music: UploadFile | None = File(None),
    music_track_id: str = Form(""),
    music_media_id: str = Form(""),
    user_id: str | None = Depends(current_user_id),
) -> TrackAnalysis:
    """Read a song before the edit is made, so its stretch can be chosen.

    Exactly one of: a library track, a song in My files, or a file — the
    last is analysed from a temporary copy and not kept.
    """
    settings = get_settings()
    if music_track_id.strip():
        try:
            path = track_path_for(music_track_id.strip())
        except HTTPException:
            raise HTTPException(status_code=422, detail="That track isn't in the library.") from None
        return await asyncio.to_thread(_library_analysis, str(path), settings.ffmpeg_binary)
    if music_media_id.strip():
        media = await media_store.get_owned(music_media_id.strip(), user_id)
        if media is None or media.kind != "audio":
            raise HTTPException(status_code=422, detail="That song isn't in your files.")
        return await asyncio.to_thread(_analysis_of, media.path, settings.ffmpeg_binary)
    if music is None:
        raise HTTPException(status_code=422, detail="Choose a song to analyse.")

    with tempfile.TemporaryDirectory() as work:
        destination = beat_edits.music_path(Path(work), Path(music.filename or "").suffix.lower())
        try:
            await uploads.save_stream(_chunks(music), destination, beat_edits.MAX_MUSIC_BYTES)
            await beat_edits.probe_audio(destination, settings.ffprobe_binary)
        except uploads.UploadRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return await asyncio.to_thread(_analysis_of, destination, settings.ffmpeg_binary)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
