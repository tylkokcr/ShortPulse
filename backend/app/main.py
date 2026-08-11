"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import RateLimitMiddleware, SupabaseAuthMiddleware
from app.api.routes import art_styles, credits, music, projects, render, uploads, voices
from app.core.config import get_settings
from app.services import db, project_store
from app.services.media_tokens import MediaTokenSigner
from app.services.render_manager import RenderTaskQueue, reconcile_interrupted_renders
from app.services.supabase_auth import SupabaseTokenVerifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Postgres is optional: without DATABASE_URL the app falls back to an
    # in-memory store, so the self-hosted path needs no infrastructure.
    pool = None
    if settings.database_url:
        pool = await db.connect(settings.database_url)
        await db.apply_migrations(pool)
    project_store.configure(pool)
    app.state.db_pool = pool

    # Anything still marked `rendering` was abandoned when the previous
    # process died. Refund and fail it before accepting new work, so the
    # user isn't left paying for a render that will never finish.
    await reconcile_interrupted_renders()

    render_queue = RenderTaskQueue(settings)
    render_queue.start()
    app.state.render_queue = render_queue
    app.state.settings = settings
    app.state.media_signer = MediaTokenSigner(
        settings.media_url_secret, ttl_s=settings.media_url_ttl_s
    )
    try:
        yield
    finally:
        await render_queue.stop()
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
app.include_router(uploads.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
