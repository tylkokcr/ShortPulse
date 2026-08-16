"""One writer at a time per project.

Nothing in this codebase locked anything before. It became worth fixing
when re-rolling a scene arrived, because that rewrites
`output/concatenated.mp4` — the file every future edit is re-burned from —
while an edit may be reading it. The loser of that race does not fail; it
produces a video timed against someone else's captions.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services import project_lock
from app.services.project_lock import ProjectBusy, hold


@pytest.fixture(autouse=True)
def _clean():
    project_lock._held.clear()
    yield
    project_lock._held.clear()


def test_a_second_claim_is_refused_rather_than_queued():
    """Queueing would leave the second caller waiting out someone else's
    ffmpeg with nothing to show, on a request that has already been
    answered slowly once."""
    with hold("proj"):
        with pytest.raises(ProjectBusy):
            with hold("proj"):
                pass


def test_the_claim_is_released_even_when_the_work_raises():
    """A failed edit must not lock the project out forever — and every
    caller here is wrapped in exception handling that turns a failure into
    an HTTP status."""
    with pytest.raises(RuntimeError, match="ffmpeg"):
        with hold("proj"):
            raise RuntimeError("ffmpeg died")

    with hold("proj"):
        pass


def test_two_projects_do_not_contend():
    with hold("one"), hold("two"):
        assert project_lock.is_held("one")
        assert project_lock.is_held("two")


def test_nothing_is_left_behind():
    """The registry is keyed by project id and would otherwise grow by one
    entry per project rendered, forever."""
    with hold("proj"):
        pass

    assert project_lock._held == set()


async def test_a_task_cannot_slip_in_while_another_holds_it():
    """The claim is a set membership test with no await between the check
    and the add, so the event loop cannot interleave two claimants. Stated
    as a test because that property is the entire safety argument."""
    started = asyncio.Event()
    refused = []

    async def first():
        with hold("proj"):
            started.set()
            await asyncio.sleep(0.05)

    async def second():
        await started.wait()
        try:
            with hold("proj"):
                pass
        except ProjectBusy:
            refused.append(True)

    await asyncio.gather(first(), second())

    assert refused == [True]
    assert not project_lock.is_held("proj")
