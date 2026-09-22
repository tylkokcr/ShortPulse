"""REST endpoints for project creation, listing, and video download."""

from __future__ import annotations

import json
import logging
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import billing_for, current_user_id, db_pool
from app.api.routes import music
from app.core.config import get_settings, project_dir
from app.core.storage import discard_project_files
from app.engines import render_engine, visual_engine
from app.schemas.project import (
    CaptionTrack,
    EditSpec,
    Layout,
    LLMConfig,
    LLMProvider,
    Project,
    ProjectConfig,
    ProjectStatus,
    SceneFeedback,
    TextOverlay,
    VisualMode,
)
from app.services import credits, editing, feedback, project_lock, project_store, regeneration
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
    settings = get_settings()

    # Refuse to sell a mode this install cannot run.
    #
    # The pipeline falls back to stock footage when generation fails, which
    # keeps a self-hosted render alive but on a paid deployment meant
    # charging three credits for a one-credit result, silently. Checking
    # here means the buyer is told before any money moves rather than
    # discovering it in the output.
    mode = VisualMode(config.visual_mode)
    reason = visual_engine.unavailable_reason(mode, settings)
    if reason is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "visual_mode_unavailable",
                "mode": str(config.visual_mode),
                "reason": reason,
                "available": [str(m) for m in visual_engine.available_modes(settings)],
            },
        )

    # `track_path` is fed to ffmpeg as an input. Anything the client sent
    # is discarded and re-derived from the id, so a request can only ever
    # name a file inside the music directory.
    config.music.track_path = (
        str(music.track_path_for(config.music.track_id)) if config.music.track_id else None
    )

    # Same rule, sharper edge: `llm.base_url` is an address this server then
    # makes a POST to. Left as the client sent it, a request could aim it at
    # cloud metadata or anything else reachable from inside the network, and
    # read the result back out of the project's error field. Which model
    # writes the script is a deployment decision anyway, not a per-request
    # one, so the whole block is replaced rather than validated.
    config.llm = LLMConfig(
        provider=LLMProvider(settings.llm_provider),
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        api_key=settings.openai_api_key,
        temperature=config.llm.temperature,
    )

    billing = billing_for(db_pool(request), user_id)

    # Refuse to spend the signup grant on a mode that bills a third party.
    #
    # The grant is there to prove the pipeline works, and stock_media
    # proves it for a fraction of a cent. Letting it buy fast_hybrid meant
    # every throwaway signup was a Replicate invoice against no revenue —
    # the giveaway stopped being our own idle compute the day generation
    # moved to an API.
    #
    # Before create_project, so a refusal leaves no row behind. Same
    # reasoning as the insufficient-credits path below, which has to
    # delete one because it cannot know early enough.
    if (
        billing is not None
        and mode not in credits.FREE_TIER_MODES
        and not await credits.may_render_paid_mode(billing.pool, billing.user_id)
    ):
        raise HTTPException(
            status_code=402,
            detail={
                "error": "purchase_required",
                "mode": str(config.visual_mode),
                "reason": credits.PURCHASE_REQUIRED_REASON,
                # What this account can render right now, which is the
                # intersection of what the install offers and what the
                # grant covers — not one or the other.
                "available": [
                    str(m)
                    for m in visual_engine.available_modes(settings)
                    if m in credits.FREE_TIER_MODES
                ],
            },
        )

    project = await project_store.create_project(config, user_id)

    if billing is not None:
        cost = credits.cost_for(config)
        try:
            await credits.spend(
                billing.pool,
                billing.user_id,
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


def _with_regeneration_state(project: Project) -> Project:
    """Answer "can a scene be re-drawn" alongside the project itself.

    Computed, never stored — it depends on what is on disk right now, and
    the answer changes on its own when the retention window closes. Set
    here rather than in the store because it costs a directory listing and
    the library grid, which loads dozens of projects, has no use for it.
    """
    can, reason = regeneration.availability(project)
    project.can_regenerate = can
    project.regenerate_blocked_reason = reason
    return project


def _with_queue_state(project: Project, request: Request) -> Project:
    """Say where an unstarted render is in line.

    Only the queue knows this — it is not in the database and cannot be,
    since it changes when *other* projects finish. Read straight off the
    live queue for the same reason the regeneration answer is read off the
    disk.
    """
    queue = getattr(request.app.state, "render_queue", None)
    if queue is None:  # self-hosted CLI use, or a test app without one
        return project
    project.queue_ahead = queue.waiting_ahead_of(project.config.id)
    project.queue_wait_s = queue.estimated_wait_s(project)
    return project


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str, request: Request, user_id: str | None = Depends(current_user_id)
) -> Project:
    project = _with_regeneration_state(await _visible_project(project_id, user_id))
    project = _with_queue_state(project, request)
    return await _with_feedback(project, db_pool(request), user_id)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str, user_id: str | None = Depends(current_user_id)
) -> None:
    await _visible_project(project_id, user_id)
    await project_store.delete_project(project_id)
    # The row was the only thing pointing at these files. Removing it
    # without them leaves the video, its audio, stills and subtitles on
    # disk forever — tens of megabytes per project that nothing will ever
    # reference again, and a user who asked for their video to be gone
    # would still have it sitting on the server.
    discard_project_files(project_id)


class StreamToken(BaseModel):
    token: str
    expires_at: int


@router.get("/{project_id}/stream-token", response_model=StreamToken)
async def get_stream_token(
    project_id: str, request: Request, user_id: str | None = Depends(current_user_id)
) -> StreamToken:
    """A credential the render-progress WebSocket can carry.

    Separate from /media-url because it has to work while the render is
    still running — that's the whole point of watching progress — whereas
    a media URL only exists once there's a file.
    """
    await _visible_project(project_id, user_id)
    token, expires_at = request.app.state.media_signer.sign(project_id)
    return StreamToken(token=token, expires_at=expires_at)


class MediaUrl(BaseModel):
    url: str          # inline — for a <video> element
    download_url: str # attachment — saves with a sensible filename
    poster_url: str   # still frame, for the library grid and <video poster>
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
        poster_url=f"/api/projects/{project_id}/poster?token={token}",
        expires_at=expires_at,
    )


class EditRequest(BaseModel):
    """What a client may change about a finished video.

    Deliberately narrower than EditSpec: `secondary_path` is absent,
    because that becomes an ffmpeg input and is only ever derived
    server-side (same rule as MusicConfig.track_path).
    """

    captions: CaptionTrack | None = None
    overlays: list[TextOverlay] = Field(default_factory=list, max_length=50)
    layout: Layout = Layout.FULL


@router.post("/{project_id}/edit", response_model=Project)
async def edit_project(
    project_id: str,
    request: Request,
    body: EditRequest,
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Apply an edit and re-burn the video.

    Free, and synchronous rather than queued. Both follow from the same
    fact: this replays the burn-in pass over footage already on disk, so it
    takes seconds and consumes nothing worth charging for. Queueing it
    would make a fast operation feel like a render.
    """
    project = await _visible_project(project_id, user_id)
    if project.status != ProjectStatus.COMPLETE:
        raise HTTPException(
            status_code=409, detail="This video hasn't finished rendering yet."
        )

    if body.layout == Layout.SPLIT_V and not (project.edit and project.edit.secondary_path):
        raise HTTPException(
            status_code=409,
            detail="Upload a clip for the bottom half before switching to split screen.",
        )

    edit = EditSpec(
        layout=body.layout,
        # Carried over from the project rather than taken from the request:
        # this string becomes an ffmpeg input, so it only ever comes from
        # the upload endpoint that wrote the file.
        secondary_path=project.edit.secondary_path if project.edit else None,
        captions=body.captions or project.captions,
        overlays=body.overlays,
        music=project.config.music,
    )

    # Held for the ffmpeg pass, not for the read above: apply_edit opens
    # concatenated.mp4 and overwrites final.mp4, and anything else doing
    # the same to this project at the same time decides the outcome by
    # whoever finishes last.
    try:
        with project_lock.hold(project_id):
            final_path = await editing.apply_edit(project, edit, get_settings())
    except project_lock.ProjectBusy as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "busy", "reason": "This video is already being changed."},
        ) from exc
    except editing.NothingToReburn as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Through the same two helpers as every other project response.
    #
    # Returned bare, this dropped `can_regenerate` to its default of false
    # and `feedback` to empty — so applying an edit made the re-roll
    # controls vanish and un-flagged every scene the user had flagged,
    # until they reloaded. Neither is stored on the row; both have to be
    # recomputed on the way out.
    saved = await project_store.update_project(
        project_id,
        edit=edit,
        # Keep `captions` as the current transcript, so re-opening the
        # editor shows what the video says rather than what it originally
        # said.
        captions=edit.captions,
        output_path=str(final_path),
    )
    return await _with_feedback(_with_regeneration_state(saved), db_pool(request), user_id)


class RegenerateSceneRequest(BaseModel):
    """What a client may change when re-rolling one scene's visual.

    Both optional and both meaning "leave it alone" when absent, so the
    plain case — the picture came out wrong, draw another — is an empty
    body. A negative prompt of "" is not absent: it clears a scene's own
    negative and falls back to the art style's.
    """

    prompt: str | None = Field(default=None, max_length=1000)
    negative_prompt: str | None = Field(default=None, max_length=1000)


@router.post("/{project_id}/scenes/{scene_index}/regenerate", response_model=Project)
async def regenerate_scene(
    project_id: str,
    request: Request,
    body: RegenerateSceneRequest,
    scene_index: int = PathParam(ge=0),
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Draw one scene again and rebuild the video around it.

    Charged, unlike /edit, because unlike /edit something expensive
    happens: a hosted image generation, and a full re-encode of the video
    to burn its captions back on. Synchronous for the same reason /edit
    is — it takes tens of seconds, and the render queue has no way to tell
    a waiting request that its turn came.
    """
    settings = get_settings()
    project = await _visible_project(project_id, user_id)

    ok, reason = regeneration.availability(project)
    if not ok:
        raise HTTPException(
            status_code=409, detail={"error": "not_regenerable", "reason": reason}
        )
    scenes = project.script.scenes if project.script else []
    if scene_index >= len(scenes):
        raise HTTPException(
            status_code=422,
            detail={"error": "no_such_scene", "scenes": len(scenes)},
        )

    billing = billing_for(db_pool(request), user_id)
    if billing is not None:
        # Same gate as creating the project: a mode the free grant does
        # not cover cannot be bought with it afterwards either.
        mode = VisualMode(project.config.visual_mode)
        # has_purchased, not may_render_paid_mode: the free trial buys one
        # finished video, and a re-roll is a second generation on top of
        # it. Asking for a pack here lands when someone has just decided
        # they want a scene fixed, which is the best moment there is.
        if mode not in credits.FREE_TIER_MODES and not await credits.has_purchased(
            billing.pool, billing.user_id
        ):
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "purchase_required",
                    "mode": str(mode),
                    "reason": credits.REROLL_PURCHASE_REQUIRED_REASON,
                },
            )

    # Held across the charge as well as the work: two re-rolls racing on
    # one scene would both read revision N, both key their charge on it,
    # and the second would be silently free.
    try:
        with project_lock.hold(project_id):
            revision = scenes[scene_index].visual.revision + 1
            if billing is not None:
                try:
                    await credits.spend(
                        billing.pool,
                        billing.user_id,
                        credits.REGENERATE_SCENE_COST,
                        project_id=project_id,
                        # Not correction:{id} or render:{id} — both are
                        # once-per-project and would make the second
                        # re-roll a no-op that charged nothing.
                        idempotency_key=f"regen:{project_id}:{scene_index}:{revision}",
                        note=f"scene {scene_index + 1} re-roll",
                        # Keeps it out of refund_project's sum. See
                        # migrations/0005.
                        reason="regenerate",
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

            try:
                final_path = await regeneration.regenerate_scene(
                    project,
                    scene_index,
                    settings,
                    revision=revision,
                    prompt=body.prompt,
                    negative_prompt=body.negative_prompt,
                )
            except Exception as exc:
                if billing is not None:
                    await _refund_regeneration(
                        billing.pool, billing.user_id, project_id, scene_index, revision
                    )
                    # The counter has to move even though nothing was
                    # produced. Leaving it where it was would make the
                    # retry reuse this attempt's idempotency key, and a
                    # replayed key charges nothing — so a failure we
                    # caused would buy the customer a free re-roll.
                    await _persist_revision(project_id, project, scene_index, revision)
                if isinstance(exc, regeneration.NotRegenerable):
                    raise HTTPException(
                        status_code=409,
                        detail={"error": "not_regenerable", "reason": str(exc)},
                    ) from exc
                logger.exception("Re-roll of scene %s failed for %s", scene_index, project_id)
                raise HTTPException(status_code=502, detail=str(exc)[:200]) from exc
    except project_lock.ProjectBusy as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "busy", "reason": "This video is already being changed."},
        ) from exc

    try:
        saved = await project_store.update_project(
            project_id,
            script=project.script,
            captions=project.captions,
            edit=project.edit,
            output_path=str(final_path),
        )
        # Feedback too: a scene flagged, then re-rolled, must not come
        # back unflagged — that is the complaint disappearing at the
        # exact moment it was acted on.
        return await _with_feedback(
            _with_regeneration_state(saved), db_pool(request), user_id
        )
    except KeyError as exc:
        # Deleted while the re-roll was running. The files are already
        # gone or will be; the charge is not, so give it back.
        if billing is not None:
            await _refund_regeneration(
                billing.pool, billing.user_id, project_id, scene_index, revision
            )
        raise HTTPException(status_code=404, detail="Project not found") from exc


async def _persist_revision(
    project_id: str, project: Project, scene_index: int, revision: int
) -> None:
    """Record an attempt that produced nothing, so the next one is new.

    Best-effort, and the only thing written on the failure path: the
    project still describes the video that is still on disk.
    """
    try:
        if project.script and scene_index < len(project.script.scenes):
            project.script.scenes[scene_index].visual.revision = revision
            await project_store.update_project(project_id, script=project.script)
    except Exception:  # noqa: BLE001
        logger.exception("Could not record the failed re-roll of scene %s", scene_index)


async def _refund_regeneration(
    pool: asyncpg.Pool, user_id: str, project_id: str, scene_index: int, revision: int
) -> None:
    """Give back a re-roll that didn't produce anything.

    A compensating entry, never an UPDATE — the ledger's own rule. And
    deliberately not refund_project, which pays back the whole render and
    can only ever fire once per project.

    Swallows its own failures for the same reason _refund_failed_render
    does: a ledger problem must not replace the error the caller actually
    needs to see.
    """
    try:
        await credits.grant(
            pool,
            user_id,
            credits.REGENERATE_SCENE_COST,
            reason="adjustment",
            idempotency_key=f"regen-refund:{project_id}:{scene_index}:{revision}",
            note=f"scene {scene_index + 1} re-roll failed",
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Could not refund the failed re-roll of scene %s on %s", scene_index, project_id
        )


class FeedbackRequest(BaseModel):
    """A verdict on a scene, or on the video as a whole.

    `scene_index` absent means the whole video. `reason` is one of a fixed
    list so the common cases stay countable — anything else goes in
    `note`, which is read rather than tallied.
    """

    scene_index: int | None = Field(default=None, ge=0)
    rating: Literal["up", "down"]
    reason: str | None = None
    note: str | None = Field(default=None, max_length=1000)


@router.post("/{project_id}/feedback", response_model=Project)
async def submit_feedback(
    project_id: str,
    request: Request,
    body: FeedbackRequest,
    user_id: str | None = Depends(current_user_id),
) -> Project:
    """Record what came out wrong.

    Free, quick, and the only signal of its kind here: the privacy page
    promises no analytics and no third-party scripts, so asking and
    keeping the answer in our own database is the honest way to learn
    whether the output is any good.

    Returns the project so the caller re-renders from one response, the
    same shape as an edit or a re-roll.
    """
    project = await _visible_project(project_id, user_id)
    pool = db_pool(request)
    if pool is None or user_id is None:
        # Self-hosted: nobody to attribute it to and nowhere to put it.
        # Not an error — there is simply no product team to tell.
        return _with_regeneration_state(project)

    if body.reason is not None and body.reason not in feedback.REASONS:
        raise HTTPException(
            status_code=422,
            detail={"error": "unknown_reason", "allowed": list(feedback.REASONS)},
        )
    scenes = project.script.scenes if project.script else []
    if body.scene_index is not None and body.scene_index >= len(scenes):
        raise HTTPException(
            status_code=422, detail={"error": "no_such_scene", "scenes": len(scenes)}
        )

    await feedback.record(
        pool,
        project_id=project_id,
        user_id=user_id,
        entry=feedback.Feedback(**body.model_dump()),
        # Denormalised on purpose — see migration 0006. The point of the
        # table is "which mode and style produce bad scenes", and a join
        # cannot answer that once the user deletes the render they
        # disliked.
        visual_mode=str(project.config.visual_mode),
        art_style=project.config.art_style,
    )
    return await _with_feedback(_with_regeneration_state(project), pool, user_id)


async def _with_feedback(
    project: Project, pool: asyncpg.Pool | None, user_id: str | None
) -> Project:
    """Attach this viewer's own verdicts, so the UI doesn't ask twice."""
    if pool is None or user_id is None:
        return project
    entries = await feedback.for_project(pool, project.config.id, user_id)
    project.feedback = [SceneFeedback(**e.model_dump()) for e in entries]
    return project


@router.get("/{project_id}/timings")
async def project_timings(
    project_id: str, user_id: str | None = Depends(current_user_id)
) -> dict:
    """Per-stage wall clock for the render.

    The pipeline has always written this next to the output, and nothing
    ever read it back. It is the most honest thing this product can show
    about itself — where the minutes actually went, on the machine that
    did the work — so it is served rather than left on disk.

    Returns an empty object rather than 404 when absent: renders from
    before this file existed, and uploads, simply have nothing to report,
    and that is not an error worth a red box in the UI.
    """
    await _visible_project(project_id, user_id)
    path = project_dir(project_id) / "timings.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable timings.json for project %s", project_id)
        return {}


@router.get("/{project_id}/poster")
async def project_poster(
    project_id: str,
    request: Request,
    token: str | None = Query(default=None),
    user_id: str | None = Depends(current_user_id),
) -> FileResponse:
    """The still frame extracted after the render.

    Same two ways in as the video itself, and deliberately the same token:
    a poster is a frame of the video, so anything that can already see the
    video can see it. Minting a second credential would imply it were more
    sensitive than the thing it is a picture of.
    """
    if token is not None:
        try:
            request.app.state.media_signer.verify(project_id, token)
        except InvalidMediaToken as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    else:
        await _visible_project(project_id, user_id)

    poster = project_dir(project_id) / "output" / "poster.jpg"
    if not poster.is_file():
        # Renders from before posters existed, and any render whose
        # thumbnail step failed. The client falls back to a placeholder.
        raise HTTPException(status_code=404, detail="No poster for this project")
    return FileResponse(poster, media_type="image/jpeg")


@router.get("/{project_id}/scenes/{scene_index}/thumb")
async def scene_thumbnail(
    project_id: str,
    request: Request,
    scene_index: int = PathParam(ge=0),
    token: str | None = Query(default=None),
    user_id: str | None = Depends(current_user_id),
) -> FileResponse:
    """One frame of one scene, so the shot list can be looked at.

    The breakdown lists a prompt per scene — "a portrait with an intense
    gaze" — which does not tell anyone which picture that produced. They
    have to scrub the player to find out, and the two controls under each
    row are useless until they have. A frame turns the list into a
    storyboard you can scan.

    Extracted on demand from the scene's own clip rather than kept from
    the render: `visuals/` is discarded on purpose and was 91% of what
    cleanup reclaims. The clip survives the retention window, and the
    picture is inside it.

    Cached, because a twelve-scene breakdown would otherwise run twelve
    ffmpeg seeks on every page load. The cache outlives the clip it came
    from — once the window closes and the clips are swept, a project that
    was looked at keeps its storyboard and one that never was has none.
    That asymmetry is fine: it costs 30KB to be generous to the first.
    """
    if token is not None:
        try:
            request.app.state.media_signer.verify(project_id, token)
        except InvalidMediaToken as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    else:
        await _visible_project(project_id, user_id)

    output = project_dir(project_id) / "output"
    cached = output / f"thumb_{scene_index:02d}.jpg"
    if not cached.is_file():
        clip = output / f"clip_{scene_index:02d}.mp4"
        if not clip.is_file():
            # An older render, or one past its retention window. The
            # client shows the prompt on its own, as it always did.
            raise HTTPException(status_code=404, detail="No frame for this scene")
        settings = get_settings()
        made = await render_engine.extract_poster(
            clip,
            cached,
            width=160,
            ffmpeg_binary=settings.ffmpeg_binary,
            ffprobe_binary=settings.ffprobe_binary,
        )
        if made is None:
            raise HTTPException(status_code=404, detail="No frame for this scene")

    return FileResponse(
        cached,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
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
