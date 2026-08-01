"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import projects, render
from app.core.config import get_settings
from app.services.render_manager import RenderTaskQueue

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    render_queue = RenderTaskQueue(settings)
    render_queue.start()
    app.state.render_queue = render_queue
    app.state.settings = settings
    try:
        yield
    finally:
        await render_queue.stop()


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

app.include_router(projects.router)
app.include_router(render.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
