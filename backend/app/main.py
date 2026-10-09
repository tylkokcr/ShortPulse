"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import RateLimitMiddleware, SupabaseAuthMiddleware
from app.api.routes import (
    art_styles,
    beat_edits,
    credits,
    media,
    music,
    projects,
    referrals,
    render,
    social,
    uploads,
    visual_modes,
    voices,
)
from app.core import monitoring, readiness
from app.core.config import get_settings
from app.services import db, media_store, project_store
from app.services import social as social_platforms
from app.services.media_tokens import MediaTokenSigner
from app.services.publish_manager import PublishQueue, configure_queue, configure_signer
from app.services.render_manager import RenderTaskQueue, resume_interrupted_renders
from app.services.social_tokens import TokenCipher
from app.services.supabase_auth import SupabaseTokenVerifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    monitoring.configure(settings)

    # Postgres is optional: without DATABASE_URL the app falls back to an
    # in-memory store, so the self-hosted path needs no infrastructure.
    pool = None
    if settings.database_url:
        pool = await db.connect(settings.database_url)
        await db.apply_migrations(pool)
    project_store.configure(pool)
    media_store.configure(pool)
    app.state.db_pool = pool

    # Logged loudly rather than raised: refusing to boot would take a
    # running service down over a setting that was already wrong, and the
    # same list is on /api/health for anything that wants to gate on it.
    readiness.log_at_startup(settings)

    render_queue = RenderTaskQueue(settings)
    render_queue.start()
    app.state.render_queue = render_queue
    # What the previous process left unfinished — running, or waiting in
    # its in-memory queue — goes back on this one's, rather than being
    # failed by a deploy. See resume_interrupted_renders.
    await resume_interrupted_renders(render_queue)
    app.state.settings = settings
    app.state.media_signer = MediaTokenSigner(
        settings.media_url_secret, ttl_s=settings.media_url_ttl_s
    )
    # Publishing shares the signer: Instagram and TikTok fetch the video
    # themselves, so a publish job needs the same signed URL the browser
    # plays from — just with a longer life on it.
    configure_signer(app.state.media_signer)

    # No secret means no publishing at all rather than tokens in plain
    # text; no configured platform means the same, with nothing to log
    # about it on a self-hosted install.
    app.state.token_cipher = (
        TokenCipher(settings.social_token_secret) if settings.social_token_secret else None
    )
    app.state.publishers = social_platforms.build_publishers(settings)
    publish_queue = PublishQueue(settings, app.state.publishers, app.state.token_cipher)
    publish_queue.start()
    # After the queue's workers exist, so a job reloaded from the database
    # has somewhere to go.
    await publish_queue.resume_after_restart()
    app.state.publish_queue = publish_queue
    configure_queue(publish_queue)

    try:
        yield
    finally:
        # A deploy waits briefly for running renders before stopping them;
        # what does not finish in time resumes on the next start.
        await render_queue.stop(drain_s=settings.shutdown_drain_s)
        await publish_queue.stop()
        await db.disconnect()


app = FastAPI(
    title="ShortPulse",
    description="Local, open-source AI video agent for short-form vertical content.",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Starlette runs middleware in reverse registration order, so this is added
# first and therefore runs *after* authentication — which is what lets it
# throttle per user rather than lumping everyone behind a NAT together.
app.add_middleware(
    RateLimitMiddleware,
    renders_per_hour=settings.render_submissions_per_hour,
    requests_per_minute=settings.api_requests_per_minute,
)

# Runs before the routes, so request.state.user_id is populated by the time
# any handler (or the billing layer behind it) asks who is calling.
app.add_middleware(
    SupabaseAuthMiddleware,
    verifier=SupabaseTokenVerifier(settings.supabase_url) if settings.supabase_url else None,
    require_auth=settings.require_auth,
    signup_grant=settings.signup_credit_grant,
)

app.include_router(projects.router)
app.include_router(render.router)
app.include_router(credits.router)
app.include_router(music.router)
app.include_router(voices.router)
app.include_router(art_styles.router)
app.include_router(visual_modes.router)
app.include_router(uploads.router)
app.include_router(beat_edits.router)
app.include_router(media.router)
app.include_router(referrals.router)
app.include_router(social.router)


@app.get("/api/health")
async def health() -> dict:
    """Liveness, plus anything about this deployment that is wrong in a way
    nothing else would report. See core/readiness.py — a deploy can refuse
    to promote a build that answers with warnings."""
    warnings = readiness.check(get_settings())
    return {
        "status": "ok",
        "ready_for_production": not warnings,
        "warnings": [{"setting": w.setting, "problem": w.problem} for w in warnings],
    }
