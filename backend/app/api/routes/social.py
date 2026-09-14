"""Connecting accounts, and publishing to them.

The awkward part of this file is the OAuth callback, and it is worth
saying why up front. Every other endpoint here is a normal authenticated
request: the browser sends a bearer token, middleware turns it into a user
id, done. The callback is not — it is a redirect *from Google*, arriving
with no header of ours on it, carrying only whatever we put in `state`.

So `state` has to be what identifies the user, and it has to be
unguessable, or anyone who could get a victim to follow a link would be
able to attach their own account to somebody else's ShortPulse. It is a
random nonce held server-side (see _PendingConnects) rather than anything
derived from the user, so nothing about who is connecting travels through
Google's URL bar.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.deps import db_pool, require_user_id
from app.core.config import get_settings
from app.services import project_store, social_store
from app.services.publish_manager import compose_description
from app.services.social.base import PublishError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/social", tags=["social"])

# How long a half-finished connect flow stays valid. Long enough to read a
# consent screen and pick an account, short enough that an abandoned one
# doesn't sit around.
_STATE_TTL_S = 600


@dataclass(frozen=True)
class _Pending:
    user_id: str
    platform: str
    expires_at: float


class _PendingConnects:
    """In-flight connect flows, keyed by nonce.

    In memory on purpose, and worth being explicit about the limits: a
    restart during the ten seconds someone spends on Google's consent
    screen loses the flow, and a second replica would not recognise a
    nonce the first one issued. Both surface as "connecting failed, try
    again", which is a retry of a ten-second action.

    The alternative — a table, or a signed cookie — buys correctness for a
    window this narrow at the cost of schema or of a cookie this app
    otherwise doesn't set. Revisit if this ever runs more than one process.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _Pending] = {}

    def issue(self, user_id: str, platform: str) -> str:
        self._sweep()
        nonce = secrets.token_urlsafe(32)
        self._entries[nonce] = _Pending(user_id, platform, time.time() + _STATE_TTL_S)
        return nonce

    def claim(self, nonce: str, platform: str) -> str | None:
        """One-shot: a nonce is consumed whether or not it matched, so a
        replayed callback cannot connect a second time."""
        self._sweep()
        entry = self._entries.pop(nonce, None)
        if entry is None or entry.platform != platform or entry.expires_at < time.time():
            return None
        return entry.user_id

    def _sweep(self) -> None:
        now = time.time()
        for nonce in [k for k, v in self._entries.items() if v.expires_at < now]:
            self._entries.pop(nonce, None)


_pending = _PendingConnects()


def _publishers(request: Request) -> dict:
    return getattr(request.app.state, "publishers", {})


def _queue(request: Request):
    return getattr(request.app.state, "publish_queue", None)


def _require_pool(request: Request):
    pool = db_pool(request)
    if pool is None:
        raise HTTPException(status_code=503, detail="Publishing needs a database.")
    return pool


# --------------------------------------------------------------------------
# What this deployment can do
# --------------------------------------------------------------------------


class PlatformOut(BaseModel):
    id: str
    connected: bool


@router.get("/platforms", response_model=list[PlatformOut])
async def list_platforms(request: Request) -> list[PlatformOut]:
    """Which platforms are configured here.

    Read by the UI to decide what to offer. A platform this deployment has
    no credentials for is absent rather than shown disabled — the same
    rule visual_modes follows, so nobody is presented with a button that
    cannot work.
    """
    return [PlatformOut(id=name, connected=True) for name in sorted(_publishers(request))]


class ConnectionOut(BaseModel):
    id: str
    platform: str
    display_name: str | None
    auto_publish: bool
    # False until something has gone out through this connection. The UI
    # uses it to explain why the first automatic post still needs a click.
    has_published: bool


@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(
    request: Request, user_id: str = Depends(require_user_id)
) -> list[ConnectionOut]:
    rows = await social_store.list_connections(_require_pool(request), user_id)
    return [
        ConnectionOut(
            id=c.id,
            platform=c.platform,
            display_name=c.display_name,
            auto_publish=c.auto_publish,
            has_published=c.first_post_at is not None,
        )
        for c in rows
    ]


# --------------------------------------------------------------------------
# Connecting
# --------------------------------------------------------------------------


class AuthorizeUrl(BaseModel):
    url: str


@router.post("/connect/{platform}", response_model=AuthorizeUrl)
async def start_connect(
    platform: str, request: Request, user_id: str = Depends(require_user_id)
) -> AuthorizeUrl:
    """Where to send the browser to grant access.

    Returned as a URL for the client to navigate to, rather than a 302,
    because this is called by fetch() — a redirect here would be followed
    by the fetch and the consent screen would arrive as unusable HTML in a
    JSON handler.
    """
    publisher = _publishers(request).get(platform)
    if publisher is None:
        raise HTTPException(status_code=404, detail=f"{platform} publishing is not available here")

    state = _pending.issue(user_id, platform)
    return AuthorizeUrl(url=publisher.authorize_url(state))


@router.get("/callback/{platform}", include_in_schema=False)
async def finish_connect(
    platform: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Where the platform sends the browser back.

    Always ends in a redirect to the app, never in a JSON body: a human is
    looking at this, having just pressed Allow. Failures are reported
    through a query parameter the connections page reads, for the same reason
    the sign-in screen reads its errors out of the URL — the alternative
    is a raw error page with no way back.
    """
    settings = get_settings()
    app_url = f"{settings.public_base_url.rstrip('/')}/connections"

    def back(problem: str | None = None) -> RedirectResponse:
        # 303 rather than 302: this was a GET, and the browser should
        # follow it as one.
        return RedirectResponse(f"{app_url}?error={problem}" if problem else app_url, status_code=303)

    if error or not code or not state:
        # The user pressed Cancel, most often. Not a failure worth an
        # alarming message.
        return back("cancelled" if error == "access_denied" else "failed")

    owner = _pending.claim(state, platform)
    if owner is None:
        return back("expired")

    publisher = _publishers(request).get(platform)
    pool = db_pool(request)
    cipher = getattr(request.app.state, "token_cipher", None)
    if publisher is None or pool is None or cipher is None:
        return back("unavailable")

    try:
        tokens, account = await publisher.exchange_code(code)
    except PublishError as exc:
        logger.warning("Connect failed for %s: %s", platform, exc)
        return back("failed")
    except Exception:
        logger.exception("Unexpected failure connecting %s", platform)
        return back("failed")

    await social_store.upsert_connection(
        pool,
        user_id=owner,
        platform=platform,
        account=account,
        tokens=tokens,
        cipher=cipher,
    )
    return back()


class ConnectionUpdate(BaseModel):
    auto_publish: bool


@router.patch("/connections/{connection_id}", status_code=204)
async def update_connection(
    connection_id: str,
    body: ConnectionUpdate,
    request: Request,
    user_id: str = Depends(require_user_id),
) -> None:
    """Turn automatic publishing on or off for one connected account."""
    changed = await social_store.set_auto_publish(
        _require_pool(request), connection_id, user_id, body.auto_publish
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Connection not found")


@router.delete("/connections/{connection_id}", status_code=204)
async def disconnect(
    connection_id: str, request: Request, user_id: str = Depends(require_user_id)
) -> None:
    removed = await social_store.revoke_connection(_require_pool(request), connection_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Connection not found")


# --------------------------------------------------------------------------
# Publishing
# --------------------------------------------------------------------------


class PostOut(BaseModel):
    id: str
    platform: str
    status: str
    title: str | None
    privacy: str
    url: str | None
    error: str | None


def _to_out(post: social_store.Post) -> PostOut:
    return PostOut(
        id=post.id,
        platform=post.platform,
        status=post.status,
        title=post.title,
        privacy=post.privacy,
        url=post.platform_url,
        error=post.error,
    )


@router.get("/posts/{project_id}", response_model=list[PostOut])
async def list_posts(
    project_id: str, request: Request, user_id: str = Depends(require_user_id)
) -> list[PostOut]:
    posts = await social_store.list_posts_for_project(_require_pool(request), project_id, user_id)
    return [_to_out(p) for p in posts]


class PublishRequest(BaseModel):
    project_id: str
    connection_id: str
    title: str = Field(max_length=100)
    description: str = Field(default="", max_length=2200)
    hashtags: list[str] = Field(default_factory=list, max_length=15)


@router.post("/posts", response_model=PostOut, status_code=202)
async def publish_now(
    body: PublishRequest, request: Request, user_id: str = Depends(require_user_id)
) -> PostOut:
    """Publish a finished project to one connected account.

    202 rather than 201: the platform has not accepted anything yet, and
    an upload takes long enough that holding the request open for it would
    time out behind the proxy. The client polls /posts/{project_id}.
    """
    pool = _require_pool(request)
    queue = _queue(request)
    if queue is None or not queue.enabled:
        raise HTTPException(status_code=503, detail="Publishing is not available here")

    # Ownership is checked against the project row rather than trusted from
    # the body — the same rule projects.py follows, and the reason a
    # request cannot publish somebody else's render to its own account.
    owner = await project_store.owner_of(body.project_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=404, detail="Project not found")

    project = await project_store.get_project(body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.output_path:
        raise HTTPException(status_code=409, detail="This project has no finished video yet")

    connection = await social_store.load_for_publish(
        pool, body.connection_id, request.app.state.token_cipher
    )
    if connection is None or connection.user_id != user_id:
        raise HTTPException(status_code=404, detail="Connection not found")

    post_id = await social_store.create_post(
        pool,
        project_id=body.project_id,
        connection_id=body.connection_id,
        user_id=user_id,
        title=body.title,
        # The licence credit is appended here too, not only on the
        # automatic path: a user editing the description in the publish
        # dialog can delete the attribution line, and it is a condition of
        # using the footage rather than a suggestion.
        description=compose_description(project, body.description),
        hashtags=body.hashtags,
        privacy="public",
        status="queued",
    )
    if post_id is None:
        raise HTTPException(
            status_code=409, detail="This video has already been published to that account"
        )

    await queue.submit(post_id)
    post = await social_store.get_post(pool, post_id)
    return _to_out(post)


@router.post("/posts/{post_id}/approve", response_model=PostOut)
async def approve(
    post_id: str, request: Request, user_id: str = Depends(require_user_id)
) -> PostOut:
    """Release a post that was held for review.

    This is what the first-post rule leads to: a connection with automatic
    publishing on, that has never published, queues its first video here
    instead of sending it.
    """
    pool = _require_pool(request)
    queue = _queue(request)
    if queue is None or not queue.enabled:
        raise HTTPException(status_code=503, detail="Publishing is not available here")

    if not await social_store.approve_post(pool, post_id, user_id):
        raise HTTPException(status_code=404, detail="Nothing to approve")

    await queue.submit(post_id)
    post = await social_store.get_post(pool, post_id)
    return _to_out(post)
