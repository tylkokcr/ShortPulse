"""A deploy restarts the API; renders should come through it."""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import get_settings
from app.schemas.project import Project, ProjectConfig, ProjectStatus
from app.services import project_store, render_manager


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path / "projects")
    projects: dict[str, Project] = {}

    async def list_resumable(max_age_s=86400):
        return [
            p for p, proj in projects.items() if proj.status in (ProjectStatus.DRAFT, ProjectStatus.RENDERING)
        ]

    async def get_project(pid):
        return projects.get(pid)

    async def update_project(pid, **updates):
        projects[pid] = projects[pid].model_copy(update=updates)
        return projects[pid]

    monkeypatch.setattr(project_store, "list_resumable", list_resumable)
    monkeypatch.setattr(project_store, "get_project", get_project)
    monkeypatch.setattr(project_store, "update_project", update_project)
    return projects


class _Queue:
    def __init__(self):
        self.submitted: list[str] = []

    async def submit(self, project):
        self.submitted.append(project.config.id)


def _add(store, status, **kwargs):
    project = Project(config=ProjectConfig(topic="t"), status=status, **kwargs)
    store[project.config.id] = project
    return project.config.id


async def test_running_and_waiting_renders_go_back_on_the_queue(store):
    running = _add(store, ProjectStatus.RENDERING)
    waiting = _add(store, ProjectStatus.DRAFT)
    done = _add(store, ProjectStatus.COMPLETE)
    queue = _Queue()

    assert await render_manager.resume_interrupted_renders(queue) == 2
    assert queue.submitted == [running, waiting]
    assert store[running].status == ProjectStatus.DRAFT
    assert store[done].status == ProjectStatus.COMPLETE


async def test_a_render_that_keeps_dying_is_failed_and_refunded_in_the_end(store, monkeypatch):
    refunded: list[str] = []

    async def refund(pool, project_id, note=None):
        refunded.append(project_id)

    monkeypatch.setattr(render_manager.db, "optional_pool", lambda: object())
    monkeypatch.setattr(render_manager.credits, "refund_project", refund)
    pid = _add(store, ProjectStatus.RENDERING)
    queue = _Queue()
    for _ in range(render_manager.MAX_RESUMES):
        await render_manager.resume_interrupted_renders(queue)
        store[pid] = store[pid].model_copy(update={"status": ProjectStatus.RENDERING})
    await render_manager.resume_interrupted_renders(queue)

    assert queue.submitted == [pid] * render_manager.MAX_RESUMES
    assert store[pid].status == ProjectStatus.FAILED and refunded == [pid]


async def test_an_extraction_cut_halfway_is_not_cut_again(store):
    pid = _add(store, ProjectStatus.RENDERING, clip_project_ids=["c1", "c2"])
    queue = _Queue()
    await render_manager.resume_interrupted_renders(queue)
    assert queue.submitted == []
    assert store[pid].status == ProjectStatus.COMPLETE


async def test_a_deploy_lets_a_running_render_finish_and_starts_nothing_new(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_concurrent_renders", 1)
    queue = render_manager.RenderTaskQueue(settings)
    finished: list[str] = []

    async def fake_generated(project, s):
        await asyncio.sleep(0.2)
        finished.append(project.config.topic)

    async def no_referral(project_id):
        return None

    monkeypatch.setattr(render_manager, "run_pipeline", fake_generated)
    monkeypatch.setattr(render_manager, "_settle_referral", no_referral)
    first = Project(config=ProjectConfig(topic="first"))
    second = Project(config=ProjectConfig(topic="second"))
    await queue.submit(first)
    await queue.submit(second)
    queue.start()
    await asyncio.sleep(0.05)
    await queue.stop(drain_s=2.0)
    assert finished == ["first"]
