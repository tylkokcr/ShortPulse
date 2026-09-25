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
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from app.api.deps import billing_for, current_user_id, db_pool
from app.core.config import get_settings, project_dir
from app.schemas.project import (
    AspectRatio,
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

# How long a stretch an extraction will read.
#
# Not a storage limit — the 200MB upload cap already bounds that — but a
# time one. Transcription is the dominant cost of an extraction and the
# only part that scales with what is read, and the price is quoted per
# clip before the file is seen. This is what keeps that quote honest:
# past this, the work behind a fixed price stops being bounded.
#
# Measured against the **processing window**, not the file. That is the
# stretch Whisper is handed, so it is the stretch that costs something; a
# two-hour recording with ten minutes picked out of it is ten minutes of
# work, and refusing it would be refusing the feature.
MAX_CLIP_SOURCE_S = 60 * 60

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


async def _chunks(upload: UploadFile, size: int = uploads.CHUNK_BYTES):
    while chunk := await upload.read(size):
        yield chunk


def _resolve_window(
    from_s: float, to_s: float | None, duration_s: float
) -> tuple[float, float]:
    """Turn the requested stretch into a concrete one, or refuse it.

    Resolved here, against the probed duration, and nowhere else. What
    gets stored is always two real seconds — never "to the end", which
    would be a config whose meaning depends on a file, and never a bound
    the client picked out of a duration the browser guessed.

    The end is clamped rather than refused. The browser reads the
    duration out of the container and ffprobe decodes it; the two
    disagree by a frame or two on plenty of real files, and refusing an
    upload over 40ms would be indefensible. A start past the end of the
    video is a different thing — that is a request for nothing — and is
    refused.
    """
    start = max(from_s, 0.0)
    end = min(duration_s if to_s is None else to_s, duration_s)

    if start >= duration_s or end <= start:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "window_outside_source",
                "reason": (
                    "That stretch isn't inside the video. Pick a start and an "
                    "end within its length."
                ),
            },
        )

    span = end - start
    windowed = to_s is not None or start > 0
    if span < clipping.MIN_SOURCE_S:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "window_too_short" if windowed else "source_too_short",
                "reason": (
                    f"Clips come out of stretches over "
                    f"{int(clipping.MIN_SOURCE_S / 60)} minutes. This one is "
                    f"{int(span)}s — widen it, or caption the video whole."
                )
                if windowed
                else (
                    f"Clips come out of videos over "
                    f"{int(clipping.MIN_SOURCE_S / 60)} minutes. This one is "
                    f"{int(span)}s — caption it whole instead."
                ),
            },
        )
    if span > MAX_CLIP_SOURCE_S:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "window_too_long" if windowed else "source_too_long",
                "reason": (
                    f"Clips are taken from up to {MAX_CLIP_SOURCE_S // 60} "
                    "minutes at a time. Narrow the stretch you picked."
                )
                if windowed
                else (
                    f"Clips come out of videos up to "
                    f"{MAX_CLIP_SOURCE_S // 60} minutes long."
                ),
            },
        )
    return start, end


@router.post("", response_model=Project, status_code=201)
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("en"),
    title: str = Form(""),
    dub_language: str = Form(""),
    clip_count: int = Form(0),
    censor_profanity: bool = Form(False),
    clip_guidance: str = Form(""),
    aspect_ratio: str = Form("9:16"),
    # The stretch of the source to read, in seconds. An empty `clip_to_s`
    # means "to the end" and is filled in from the probe below, so what
    # gets stored is always a concrete window — see `_resolve_window`.
    clip_from_s: float = Form(0),
    clip_to_s: float | None = Form(None),
    # JSON in a form field: the file forces multipart, and this is a
    # nested object. Empty keeps the schema's defaults, which is what an
    # older client sends and what a self-hosted script that posts a file
    # and nothing else should still get.
    subtitles: str = Form(""),
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Accept a video, then queue it for transcription and caption burn-in.

    Order matters here. The id is chosen first, because it is what gives
    the file a server-chosen directory to land in — the client's filename
    never reaches the filesystem. The file is written and probed next, and
    only then is the project row created: the config it is created with
    has to describe the video that actually arrived, and the processing
    window cannot be resolved against a duration nobody has measured yet.
    The charge happens last of all, so a rejected upload never costs a
    credit.

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

    # Validated here rather than left to pydantic so the refusal names the
    # field and lists what is allowed, the same as an unsupported dub
    # language does — a raw enum error names neither.
    try:
        ratio = AspectRatio(aspect_ratio.strip())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_aspect_ratio",
                "aspect_ratio": aspect_ratio,
                "supported": [r.value for r in AspectRatio],
            },
        ) from None

    clips = max(clip_count, 0)

    # Only an extraction reframes. The upload pipeline deliberately leaves
    # the picture alone — someone captioning a video they shot gets their
    # own framing back — so a ratio stored on a caption job would be a
    # value that lies about what was rendered. `resolution_for` carries
    # the scar from the last time that happened: it was "accepted by the
    # API and stored on every project long before anything read it".
    if ratio is not AspectRatio.VERTICAL_9_16 and not clips:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "aspect_ratio_without_clips",
                "reason": (
                    "Captioning leaves the picture as it was filmed. Pick a frame "
                    "when you cut the video into clips."
                ),
            },
        )

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

    # Chosen before the file is read, because it is what names the
    # directory the file goes into. The row it belongs to is created
    # further down, once there is a probed video to describe.
    project_id = str(uuid.uuid4())
    paths = project_dir(project_id)

    suffix = Path(file.filename or "").suffix.lower()
    destination = uploads.source_path_for(paths, suffix)

    # Everything from here on can leave a file on disk that nothing will
    # ever read, and past `create_project` a row to go with it. One
    # unwind rather than a `delete_project` beside each refusal: there
    # are seven of them now, and the next one added would be the one that
    # forgot.
    created = False
    try:
        try:
            await uploads.save_stream(_chunks(file), destination)
            probed = await uploads.probe(destination, settings.ffprobe_binary)
        except uploads.UploadRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        logger.info(
            "Accepted upload for %s: %dx%d, %.1fs, audio=%s",
            project_id,
            probed.width,
            probed.height,
            probed.duration_s,
            probed.has_audio,
        )
        if not probed.has_audio:
            raise HTTPException(
                status_code=422,
                detail="That video has no audio track, so there is no speech to caption.",
            )

        # Resolved after the probe and before the charge, because until
        # the file is on disk its real duration is whatever the client
        # claimed.
        window = _resolve_window(clip_from_s, clip_to_s, probed.duration_s) if clips else None

        config = ProjectConfig(
            id=project_id,
            topic=title.strip() or (file.filename or "Uploaded video"),
            source=ProjectSource.UPLOAD,
            language=language,
            dub_language=dub or None,
            clip_count=clips or None,
            censor_profanity=censor_profanity,
            # Only meaningful for an extraction. Carried on any upload rather
            # than refused, because a client that sends it with no clip count
            # has made a harmless mistake, not a dangerous one.
            clip_guidance=clip_guidance.strip(),
            aspect_ratio=ratio,
            # Left at the defaults without clips, for the reason the frame
            # is: captioning reads the whole video, so a window stored on
            # one would describe work that never happened.
            clip_from_s=window[0] if window else 0,
            clip_to_s=window[1] if window else None,
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
                    note="autocaption",
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
            await project_store.update_project(config.id, credits_cost=cost)

        project = await project_store.update_project(config.id, source_path=str(destination))
    except Exception:
        if created:
            await project_store.delete_project(project_id)
        shutil.rmtree(paths, ignore_errors=True)
        raise

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
