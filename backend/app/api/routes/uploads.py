"""Upload a video and have it captioned.

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

from app.api.deps import billing_enabled, current_user_id, db_pool
from app.core.config import get_settings, project_dir
from app.schemas.project import Project, ProjectConfig, ProjectSource
from app.services import credits, project_store, uploads

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
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Accept a video, then queue it for transcription and caption burn-in.

    Order matters here. The project row is created first so the file has a
    server-chosen directory to land in — the client's filename never
    reaches the filesystem. The charge happens only after the file is on
    disk and has been confirmed to be real video, so a rejected upload
    never costs a credit.
    """
    settings = get_settings()

    config = ProjectConfig(
        topic=title.strip() or (file.filename or "Uploaded video"),
        source=ProjectSource.UPLOAD,
        language=language,
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
