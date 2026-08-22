"""Where a render is in line, and whether anyone can find out.

A queued render looks exactly like a stuck one from the outside. The row
sits at `draft` because no worker has touched it, no progress event is
emitted for the same reason, and the page shows one waiting state whether
the answer is ten seconds or ninety minutes.

That gap is not hypothetical at this size. The production host runs two
renders at once and a fast_hybrid medium takes about five and a half
minutes on it, so the tenth person in line waits half an hour — and a
launch that works is exactly what produces a tenth person.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import get_settings
from app.schemas.project import ProjectConfig, VideoLength, VisualMode
from app.services.render_manager import RenderTaskQueue


def _project(**kwargs):
    from app.schemas.project import Project

    return Project(config=ProjectConfig(topic="honey", **kwargs))


@pytest.fixture
def queue(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_concurrent_renders", 2)
    return RenderTaskQueue(settings)


async def test_a_queued_render_knows_how_many_are_ahead(queue):
    projects = [_project() for _ in range(4)]
    for p in projects:
        await queue.submit(p)

    assert [queue.waiting_ahead_of(p.config.id) for p in projects] == [0, 1, 2, 3]


async def test_being_next_is_not_the_same_as_not_being_queued(queue):
    """0 and None are different answers and the UI renders them
    differently — "you're next" versus saying nothing at all."""
    queued = _project()
    await queue.submit(queued)

    assert queue.waiting_ahead_of(queued.config.id) == 0
    assert queue.waiting_ahead_of("never-submitted") is None


async def test_a_render_that_started_is_no_longer_waiting(queue, monkeypatch):
    """Once a worker picks it up the honest answer is None, not 0.

    Reported as 0 it would keep telling someone they are about to start
    for the entire five minutes they are already rendering.
    """
    started = asyncio.Event()

    async def fake_pipeline(project, settings):
        started.set()
        await asyncio.sleep(3600)  # held open, so it stays "running"

    monkeypatch.setattr("app.services.render_manager.run_pipeline", fake_pipeline)

    project = _project()
    await queue.submit(project)
    queue.start()
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        assert queue.waiting_ahead_of(project.config.id) is None
    finally:
        await queue.stop()


async def test_the_estimate_grows_with_the_line(queue):
    first, second, third = (_project() for _ in range(3))
    for p in (first, second, third):
        await queue.submit(p)

    waits = [queue.estimated_wait_s(p) for p in (first, second, third)]

    assert waits[0] < waits[2], waits
    # Two workers, so the second starts alongside the first rather than
    # after it — the line advances in pairs and the estimate must too.
    assert waits[0] == waits[1], waits


async def test_a_longer_video_is_a_longer_wait(queue):
    short = _project(video_length=VideoLength.SHORT, visual_mode=VisualMode.FAST_HYBRID)
    long_ = _project(video_length=VideoLength.LONG, visual_mode=VisualMode.FAST_HYBRID)
    await queue.submit(short)
    await queue.submit(long_)

    assert queue.estimated_wait_s(long_) > queue.estimated_wait_s(short)


async def test_stock_media_is_estimated_faster_than_generated(queue):
    """The measured difference is large — 22-92s against 242-362s — so an
    estimate that ignored the mode would be wrong by a factor of five for
    whichever one it was not tuned to."""
    stock = _project(visual_mode=VisualMode.STOCK_MEDIA)
    generated = _project(visual_mode=VisualMode.FAST_HYBRID)
    await queue.submit(stock)
    await queue.submit(generated)

    assert queue.estimated_wait_s(stock) < queue.estimated_wait_s(generated)


async def test_nothing_is_reported_for_a_project_never_queued(queue):
    assert queue.estimated_wait_s(_project()) is None


# --- does it actually reach the page ------------------------------------


async def test_the_api_reports_the_position(queue, monkeypatch, tmp_path):
    """The wiring, not the arithmetic.

    Everything above tests a queue object nobody can see. This asserts the
    number survives the trip to the response the polling page reads, which
    is the only part the waiting person experiences.
    """
    import httpx
    from fastapi import FastAPI

    from app.api.deps import current_user_id
    from app.api.routes import projects as projects_route
    from app.services import project_store

    project_store.configure(None)  # in-memory store
    first = await project_store.create_project(ProjectConfig(topic="first"))
    second = await project_store.create_project(ProjectConfig(topic="second"))
    await queue.submit(first)
    await queue.submit(second)

    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = None
    app.state.render_queue = queue
    app.dependency_overrides[current_user_id] = lambda: None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get(f"/api/projects/{second.config.id}")).json()

    assert body["queue_ahead"] == 1
    assert body["queue_wait_s"] > 0


async def test_an_app_without_a_queue_says_nothing(monkeypatch):
    """Self-hosted CLI runs and tests build apps with no queue attached.
    Reporting 0 there would claim a position in a line that doesn't
    exist."""
    import httpx
    from fastapi import FastAPI

    from app.api.deps import current_user_id
    from app.api.routes import projects as projects_route
    from app.services import project_store

    project_store.configure(None)
    project = await project_store.create_project(ProjectConfig(topic="alone"))

    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = None
    app.dependency_overrides[current_user_id] = lambda: None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get(f"/api/projects/{project.config.id}")).json()

    assert body["queue_ahead"] is None
