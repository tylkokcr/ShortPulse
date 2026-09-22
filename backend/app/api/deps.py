"""Request-scoped dependencies: who is calling, and where to bill them.

ShortPulse runs in two shapes from the same codebase:

  * **Self-hosted.** No database, no accounts, no billing. Renders cost the
    operator their own electricity, so charging credits would be nonsense.
  * **Hosted.** Every request belongs to an authenticated user and every
    render is paid for out of that user's credit balance.

Both are decided by these two dependencies rather than by branching all
over the route handlers. `current_user_id` is the single seam where
authentication plugs in; until the Supabase JWT verifier lands it returns
None, which every caller already reads as "self-hosted, nothing to bill".
"""

from __future__ import annotations

from typing import NamedTuple

import asyncpg
from fastapi import HTTPException, Request


async def current_user_id(request: Request) -> str | None:
    """The authenticated user, or None when the install has no auth.

    Returning None is a legitimate answer, not a failure: it is what a
    self-hosted install looks like. Endpoints that genuinely require an
    identity should use `require_user_id` instead of guessing.
    """
    return getattr(request.state, "user_id", None)


async def require_user_id(request: Request) -> str:
    user_id = await current_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def db_pool(request: Request) -> asyncpg.Pool | None:
    """The Postgres pool, or None when running without a database."""
    return getattr(request.app.state, "db_pool", None)


class Billing(NamedTuple):
    """Somewhere to record a charge, and someone to charge."""

    pool: asyncpg.Pool
    user_id: str


def billing_for(pool: asyncpg.Pool | None, user_id: str | None) -> Billing | None:
    """The pair needed to charge, or None when this install cannot.

    Credits only apply when there is both somewhere to record them and
    someone to charge. Either one missing means this is a self-hosted
    install and renders are free.

    It returns the pair rather than a bool so that the question and its
    answer travel together: every caller that passes the check needs both
    values immediately afterwards, and handing them back already narrowed
    is what stops a `None` from reaching `credits.spend` — the shape of
    mistake that has cost us deploys.
    """
    if pool is None or user_id is None:
        return None
    return Billing(pool, user_id)
