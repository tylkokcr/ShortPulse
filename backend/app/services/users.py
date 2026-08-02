"""Mirroring Supabase users into our own tables.

Supabase owns `auth.users`; we keep `app_users` alongside it with the same
ids. The duplication is deliberate — projects and ledger entries have
foreign keys into it, and pointing those at a schema managed by an external
service means an upgrade on their side could break referential integrity on
ours.

Rows appear on first authenticated request rather than through a signup
webhook, so there is no window where a valid user exists to Supabase but
not to us, and nothing to reconcile if a webhook is missed.
"""

from __future__ import annotations

import logging

import asyncpg

from app.services import credits

logger = logging.getLogger(__name__)


async def ensure_user(
    conn: asyncpg.Connection | asyncpg.Pool,
    user_id: str,
    email: str | None = None,
    *,
    signup_grant: int = 0,
) -> None:
    """Make sure `app_users` has this user, granting starter credits once.

    Called on every authenticated request, so both halves must be cheap and
    idempotent. The insert no-ops after the first time; the grant carries an
    idempotency key, so replaying it can never top the account up again —
    including across concurrent first requests from the same user.
    """
    created = await conn.fetchval(
        """
        insert into app_users (id, email) values ($1, $2)
        on conflict (id) do nothing
        returning id
        """,
        user_id,
        email,
    )
    if created is None:
        return

    logger.info("First sight of user %s", user_id)
    if signup_grant > 0:
        await credits.grant(
            conn,
            user_id,
            signup_grant,
            idempotency_key=f"signup:{user_id}",
            note="signup grant",
        )
