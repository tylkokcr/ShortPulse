"""One writer at a time per project.

Editing and re-rolling a scene both rewrite files a finished project is
still serving: `output/final.mp4`, and — for a re-roll —
`output/concatenated.mp4`, which is the source every future edit is
re-burned from. Two of those running at once on one project is not a race
you lose slowly. `apply_edit` opens the concatenated cut as an ffmpeg
input while a re-roll is replacing it, and whichever finishes last
overwrites the other's `final.mp4` with a video timed against the other's
captions.

Refusing rather than queueing, deliberately. Both operations take tens of
seconds and both are synchronous HTTP requests; a caller who waits for the
lock and then waits for the work has already timed out, and would be told
nothing in the meantime. A 409 the client can retry is a better answer
than a request that hangs.

A set and not an asyncio.Lock, for the same reason. A Lock's job is to
make waiters queue, which is the behaviour being refused here — and using
one for its `locked()` flag alone means reaching into its internals to
avoid the awaiting it exists to do. The event loop is single-threaded and
nothing below awaits between the check and the claim, so the set is
already atomic with respect to every other task.

Single-process, like everything else here — the rate limiter's buckets
(services/rate_limit.py) and connection_manager's socket registry make the
same assumption. Running two API containers against one storage volume
needs `pg_try_advisory_xact_lock` on the project id instead; nothing in
this deployment does that today.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


class ProjectBusy(RuntimeError):
    """Someone else is already writing this project's files."""


_held: set[str] = set()


@contextmanager
def hold(project_id: str) -> Iterator[None]:
    """Claim a project for the duration of the block, or raise ProjectBusy."""
    if project_id in _held:
        raise ProjectBusy(project_id)
    _held.add(project_id)
    try:
        yield
    finally:
        _held.discard(project_id)


def is_held(project_id: str) -> bool:
    """For tests and diagnostics. Not a check to act on — anything that
    branches on this has a race between asking and doing; use `hold`."""
    return project_id in _held
