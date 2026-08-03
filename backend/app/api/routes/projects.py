"""REST endpoints for project creation, listing, and video download."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import billing_enabled, current_user_id, db_pool
from app.schemas.project import Project, ProjectConfig
from app.services import credits, project_store
from app.services.media_tokens import InvalidMediaToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=Project, status_code=201)
async def create_project(
    config: ProjectConfig,
    request: Request,
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Create a project, charge for it, and enqueue it for rendering.

    The charge happens here rather than inside the pipeline so the user
    learns they cannot afford a render immediately, instead of watching a
    queued job fail minutes later. On a self-hosted install there is no
    user and no database, so this is free and the ledger is never touched.
    """
    pool = db_pool(request)
    project = await project_store.create_project(config, user_id)

    if billing_enabled(pool, user_id):
        cost = credits.cost_for(config)
        try:
            await credits.spend(
                pool,
                user_id,
                cost,
                project_id=config.id,
                # Keyed on the project, so a retried request for the same
                # project can never be charged twice.
                idempotency_key=f"render:{config.id}",
                # ProjectConfig uses use_enum_values, so these are already str.
                note=f"{config.visual_mode}/{config.video_length}",
            )
        except credits.InsufficientCredits as exc:
            # Nothing was charged and nothing was queued, so the project
            # row is pure noise — drop it rather than leaving the user a
            # draft they never asked to keep.
            await project_store.delete_project(config.id)
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_credits",
                    "balance": exc.balance,
                    "required": exc.required,
                },
            ) from exc
        project = await project_store.update_project(config.id, credits_cost=cost)

    await request.app.state.render_queue.submit(project)
    return project


@router.get("", response_model=list[Project])
async def list_projects(user_id: str | None = Depends(current_user_id)) -> list[Project]:
    return await project_store.list_projects(user_id)


async def _visible_project(project_id: str, user_id: str | None) -> Project:
    """Fetch a project the caller is allowed to see.

    A project with no owner belongs to a self-hosted install and is open to
    whoever can reach the API — that is the whole model there. Once a
    project has an owner, only that owner may touch it. Written this way
    round so an unauthenticated request can never reach an owned project:
    the check keys off the row, not off the caller.

    Denied access returns 404 rather than 403, so project ids can't be
    probed for existence.
    """
    project = await project_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    owner = await project_store.owner_of(project_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str, user_id: str | None = Depends(current_user_id)
) -> Project:
    return await _visible_project(project_id, user_id)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str, user_id: str | None = Depends(current_user_id)
) -> None:
    await _visible_project(project_id, user_id)
    await project_store.delete_project(project_id)


class MediaUrl(BaseModel):
    url: str          # inline — for a <video> element
    download_url: str # attachment — saves with a sensible filename
    expires_at: int


@router.get("/{project_id}/media-url", response_model=MediaUrl)
async def get_media_url(
    project_id: str, request: Request, user_id: str | None = Depends(current_user_id)
) -> MediaUrl:
    """Mint a short-lived URL the browser can put in a <video> tag.

    Ownership is checked here, on a request that *can* carry an
    Authorization header. The URL this returns is what actually fetches the
    bytes, and it proves nothing about who is asking beyond holding a
    signature for this one project.
    """
    project = await _visible_project(project_id, user_id)
    if not project.output_path:
        raise HTTPException(status_code=409, detail="Render is not complete yet")

    token, expires_at = request.app.state.media_signer.sign(project_id)
    return MediaUrl(
        url=f"/api/projects/{project_id}/download?token={token}",
        download_url=f"/api/projects/{project_id}/download?token={token}&download=1",
        expires_at=expires_at,
    )


@router.get("/{project_id}/download")
async def download_project_video(
    project_id: str,
    request: Request,
    token: str | None = Query(default=None),
    download: bool = Query(default=False),
    user_id: str | None = Depends(current_user_id),
) -> FileResponse:
    """Serve the rendered video.

    Two ways in, because the two callers can't both use the same one: an
    API client sends a bearer token in the header, while a <video> tag or a
    download navigation can only carry a signed token in the URL.
    """
    if token is not None:
        try:
            request.app.state.media_signer.verify(project_id, token)
        except InvalidMediaToken as exc:
            # 403, not 404: the caller has a link that was real once, and
            # "get a fresh one" is the actionable answer.
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        project = await project_store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    else:
        project = await _visible_project(project_id, user_id)

    if not project.output_path:
        raise HTTPException(status_code=409, detail="Render is not complete yet")

    # Inline unless a download was explicitly asked for. This is not
    # cosmetic: Chrome refuses to play a resource served as
    # `Content-Disposition: attachment` in a <video> element, so serving
    # everything as an attachment leaves the player spinning forever with
    # no error. Passing `filename=` to FileResponse forces attachment, so
    # the header is set by hand.
    name = f"{project.config.topic[:40].strip().replace(' ', '_') or project_id}.mp4"
    disposition = "attachment" if download else "inline"
    return FileResponse(
        project.output_path,
        media_type="video/mp4",
        headers={"Content-Disposition": f'{disposition}; filename="{name}"'},
    )
