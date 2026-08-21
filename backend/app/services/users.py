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

logger = logging.getLogger(__name__)


async def ensure_user(
    conn: asyncpg.Connection | asyncpg.Pool,
    user_id: str,
    email: str | None = None,
    *,
    signup_grant: int = 0,
) -> None:
    """Make sure `app_users` has this user, granting starter credits once.

    Called on every authenticated request, so it must be cheap and
    idempotent. The insert no-ops after the first time, and the grant
    carries an idempotency key, so replaying can never top an account up
    again.

    One statement rather than two, and that is the whole point of it.

    A new account's first authenticated request is never alone: AccountBar
    asks for the balance the moment a session appears while the editor
    asks for its own things, so several requests arrive together for a user
    the database has never seen, and each runs this function. Done as two
    statements against a pool, the first commits the row and the sibling
    requests — blocked on that insert — wake up the instant it lands, see a
    conflict, and return *before* the grant they are about to depend on
    exists. Whichever of them was fetching the balance then reads zero, and
    a brand-new account is shown "You have 0. Pick a cheaper visual style"
    with ten credits sitting in the ledger.

    Folding the grant into the same statement closes it: the conflicting
    sibling now waits on a transaction that carries both, so by the time it
    is told the row already exists, the credits already exist too. The
    grant's own idempotency key still guards against a second one.
    """
    granted = await conn.fetchval(
        """
        with created as (
            insert into app_users (id, email) values ($1, $2)
            on conflict (id) do nothing
            returning id
        ),
        granted as (
            insert into credit_entries (user_id, delta, reason, idempotency_key, note)
            select id, $3, 'grant', 'signup:' || id, 'signup grant'
            from created
            where $3 > 0
            on conflict (user_id, idempotency_key) where idempotency_key is not null
            do nothing
            returning user_id
        )
        select count(*) from granted
        """,
        user_id,
        email,
        signup_grant,
    )
    if granted:
        logger.info("First sight of user %s (granted %s credits)", user_id, signup_grant)
