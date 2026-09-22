"""Upload a video and have it captioned, or dubbed.

The second way into the product. Instead of describing a video and having
one generated, the user brings footage they already shot and asks only for
the captioning — the part of the pipeline that is genuinely hard to do by
hand, because it needs word-level timing.

Everything downstream treats the result as an ordinary project: same
progress WebSocket, same preview, same library, same editing. See
`ProjectSource` for why that unification is worth having.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from app.api.deps import billing_enabled, current_user_id, db_pool
from app.core.config import get_settings, project_dir
from app.schemas.project import (
    EditSpec,
    LLMConfig,
    LLMProvider,
    Project,
    ProjectConfig,
    ProjectSource,
    SubtitleStyle,
)
from app.services import clipping, credits, project_store, uploads

# Mirrors the schema's own bound. Duplicated so the refusal names the
# limit instead of arriving as a pydantic field error about `le`.
MAX_CLIPS = 5

# How long a source an extraction will read.
#
# Not a storage limit — the 200MB upload cap already bounds that — but a
# time one. Transcription is the dominant cost of an extraction and the
# only part that scales with the source, and the price is quoted per clip
# before the file is seen. This is what keeps that quote honest: past
# this, the work behind a fixed price stops being bounded.
MAX_CLIP_SOURCE_S = 60 * 60

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


async def _chunks(upload: UploadFile, size: int = uploads.CHUNK_BYTES):
    while chunk := await upload.read(size):
        yield chunk


@router.post("", response_model=Project, status_code=201)
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("en"),
    title: str = Form(""),
    dub_language: str = Form(""),
    clip_count: int = Form(0),
    # JSON in a form field: the file forces multipart, and this is a
    # nested object. Empty keeps the schema's defaults, which is what an
    # older client sends and what a self-hosted script that posts a file
    # and nothing else should still get.
    subtitles: str = Form(""),
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Accept a video, then queue it for transcription and caption burn-in.

    Order matters here. The project row is created first so the file has a
    server-chosen directory to land in — the client's filename never
    reaches the filesystem. The charge happens only after the file is on
    disk and has been confirmed to be real video, so a rejected upload
    never costs a credit.

    `dub_language` turns this into a dub: the speech is translated and
    re-spoken in that language over the original picture. `language` still
    describes what the video is in, because that is what the transcription
    pass is told.

    `clip_count` turns it into an extraction instead: the transcript is
    read for the moments that stand up on their own, each is cut out, and
    each becomes a project of its own. This one keeps their ids and no
    video.
    """
    settings = get_settings()

    dub = dub_language.strip().lower()
    if dub:
        # Checked here rather than in the schema because the catalogue of
        # voices lives in audio_engine, which imports the schema. Checked
        # before the file is written and long before anything is charged.
        from app.engines.audio_engine import PIPER_VOICE_BY_LANGUAGE

        if dub not in PIPER_VOICE_BY_LANGUAGE:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unsupported_dub_language",
                    "language": dub,
                    "supported": sorted(PIPER_VOICE_BY_LANGUAGE),
                },
            )
        if dub == language.strip().lower():
            # Not a dub, and the case we deliberately do not offer: with
            # the speaker's own language coming out of a different mouth,
            # mismatched lips read as a broken video rather than as
            # dubbing. See services/dubbing.py.
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "same_language_dub",
                    "reason": (
                        "Dubbing replaces the speech with another language. "
                        "To keep this language, upload it for captions instead."
                    ),
                },
            )

    clips = max(clip_count, 0)
    if clips:
        if dub:
            # Both would mean dubbing each clip, which is a reasonable
            # thing to want and not what either code path does today.
            # Refused rather than silently doing one of them.
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "dub_and_clips",
                    "reason": "Take the clips first, then dub the ones you keep.",
                },
            )
        if clips > MAX_CLIPS:
            raise HTTPException(
                status_code=422,
                detail={"error": "too_many_clips", "max": MAX_CLIPS},
            )

    config = ProjectConfig(
        topic=title.strip() or (file.filename or "Uploaded video"),
        source=ProjectSource.UPLOAD,
        language=language,
        dub_language=dub or None,
        clip_count=clips or None,
    )

    if subtitles.strip():
        # Validated rather than trusted: this arrives as a string, and a
        # malformed one should be a 422 naming the field rather than a
        # render that silently falls back to the default and leaves the
        # user wondering why the style they picked did nothing — which is
        # exactly the bug this parameter exists to fix.
        try:
            config.subtitles = SubtitleStyle.model_validate_json(subtitles)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail="That caption style isn't valid."
            ) from exc
    # The translation runs through the same model the script engine uses,
    # and like there it comes from settings rather than from the request —
    # this endpoint takes no llm block, and it should stay that way.
    config.llm = LLMConfig(
        provider=LLMProvider(settings.llm_provider),
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        api_key=settings.openai_api_key,
        temperature=config.llm.temperature,
    )
    # Nothing was generated, so there is no soundtrack decision to inherit.
    # Adding music under someone's own footage without being asked would be
    # a surprising thing to do to their audio.
    config.music.enabled = False

    project = await project_store.create_project(config, user_id)
    paths = project_dir(config.id)

    suffix = Path(file.filename or "").suffix.lower()
    destination = uploads.source_path_for(paths, suffix)

    try:
        await uploads.save_stream(_chunks(file), destination)
        probed = await uploads.probe(destination, settings.ffprobe_binary)
    except uploads.UploadRejected as exc:
        await project_store.delete_project(config.id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        await project_store.delete_project(config.id)
        raise

    logger.info(
        "Accepted upload for %s: %dx%d, %.1fs, audio=%s",
        config.id,
        probed.width,
        probed.height,
        probed.duration_s,
        probed.has_audio,
    )
    if not probed.has_audio:
        await project_store.delete_project(config.id)
        raise HTTPException(
            status_code=422,
            detail="That video has no audio track, so there is no speech to caption.",
        )

    if clips:
        # Both bounds are checked here, after the probe and before the
        # charge, because until the file is on disk its real duration is
        # whatever the client claimed.
        if probed.duration_s < clipping.MIN_SOURCE_S:
            await project_store.delete_project(config.id)
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "source_too_short",
                    "reason": (
                        f"Clips come out of videos over "
                        f"{int(clipping.MIN_SOURCE_S / 60)} minutes. This one is "
                        f"{int(probed.duration_s)}s — caption it whole instead."
                    ),
                },
            )
        if probed.duration_s > MAX_CLIP_SOURCE_S:
            await project_store.delete_project(config.id)
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "source_too_long",
                    "reason": (
                        f"Clips come out of videos up to "
                        f"{MAX_CLIP_SOURCE_S // 60} minutes long."
                    ),
                },
            )

    pool = db_pool(request)
    if billing_enabled(pool, user_id):
        cost = credits.cost_for(config)
        try:
            await credits.spend(
                pool,
                user_id,
                cost,
                project_id=config.id,
                idempotency_key=f"render:{config.id}",
                note="autocaption",
            )
        except credits.InsufficientCredits as exc:
            await project_store.delete_project(config.id)
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "balance": exc.balance,
                    "required": exc.required,
                },
            ) from exc
        await project_store.update_project(config.id, credits_cost=cost)

    project = await project_store.update_project(config.id, source_path=str(destination))
    await request.app.state.render_queue.submit(project)
    return project


@router.post("/{project_id}/secondary", response_model=Project)
async def upload_secondary_clip(
    project_id: str,
    file: UploadFile = File(...),
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Attach the bottom half of a split-screen layout.

    Stored against the project rather than uploaded with the edit, because
    the file is large and the edit is a small JSON document the user may
    apply repeatedly while adjusting captions. Uploading once and
    re-rendering many times is the shape that fits.

    The path recorded here is the only one the renderer will use — the edit
    endpoint takes a layout, never a location.
    """
    from app.api.routes.projects import _visible_project

    settings = get_settings()
    project = await _visible_project(project_id, user_id)

    paths = project_dir(project_id)
    suffix = Path(file.filename or "").suffix.lower()
    destination = uploads.source_path_for(paths, suffix, name="secondary")

    try:
        await uploads.save_stream(_chunks(file), destination)
        await uploads.probe(destination, settings.ffprobe_binary)
    except uploads.UploadRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    edit = project.edit or EditSpec(captions=project.captions)
    edit = edit.model_copy(update={"secondary_path": str(destination)})
    return await project_store.update_project(project_id, edit=edit)
