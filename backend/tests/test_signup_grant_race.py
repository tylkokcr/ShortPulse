"""The first page load after signing up, with its requests in parallel.

A new account's first authenticated request is never alone. AccountBar
asks for the balance the moment a session appears, and the editor asks
for its own things at the same moment, so several requests arrive
together carrying a token for a user the database has never seen. Each
one runs ensure_user on the way in.

What a stranger reported: signed up, landed on the editor, saw 0 credits
and "You have 0. Pick a cheaper visual style". The ledger said 10. The
grant had worked — it just wasn't visible yet to the request that asked.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest

from app.services import credits, db, users

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)

GRANT = 10
# One request creates the account; the others arrive while it is still
# working. More than two because the real first load fires several.
PARALLEL_REQUESTS = 6


@pytest.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(TEST_DSN, min_size=2, max_size=12)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres at {TEST_DSN}: {exc}")
    await db.apply_migrations(p)
    yield p
    await p.close()


async def test_no_request_ever_sees_an_ungranted_balance(pool):
    """Every request that got past the middleware must see the credits.

    This is the guarantee ensure_user owes its callers. Granting once is
    necessary but not sufficient: a request that returns from ensure_user
    and then reads a balance of 0 renders a header saying the account is
    empty, which is what the user sees and believes.

    A property check rather than the decisive one. Left to chance the
    window is a fraction of a millisecond on a local socket, so this
    passed against the broken implementation the first time it was
    written — the version that reproduced the bug had to delay the grant
    by hand, and there is no longer a separate grant call to delay.
    test_the_account_and_its_credits_land_in_one_statement is what
    actually pins the fix; this one covers the surrounding behaviour.
    """
    user_id = str(uuid.uuid4())

    async def one_request() -> int:
        await users.ensure_user(pool, user_id, "race@test.local", signup_grant=GRANT)
        # Exactly what the /api/credits route does next.
        return await credits.balance(pool, user_id)

    balances = await asyncio.gather(*(one_request() for _ in range(PARALLEL_REQUESTS)))

    assert balances == [GRANT] * PARALLEL_REQUESTS, (
        f"a first-load request saw {min(balances)} credits: the account was "
        "created by a sibling request whose grant had not committed yet"
    )


async def test_the_grant_still_happens_exactly_once(pool):
    """The property the early return was protecting. Whatever fixes the
    race must not buy it by topping the account up twice."""
    user_id = str(uuid.uuid4())

    await asyncio.gather(
        *(
            users.ensure_user(pool, user_id, "once@test.local", signup_grant=GRANT)
            for _ in range(PARALLEL_REQUESTS)
        )
    )

    rows = await pool.fetchval(
        "select count(*) from credit_entries where user_id = $1 and reason = 'grant'",
        user_id,
    )
    assert rows == 1
    assert await credits.balance(pool, user_id) == GRANT


async def test_a_returning_user_is_not_granted_again(pool):
    """Spending down to zero must not look like a fresh signup."""
    user_id = str(uuid.uuid4())
    await users.ensure_user(pool, user_id, "returning@test.local", signup_grant=GRANT)
    await credits.spend(pool, user_id, GRANT, idempotency_key=f"render:{uuid.uuid4()}")
    assert await credits.balance(pool, user_id) == 0

    await users.ensure_user(pool, user_id, "returning@test.local", signup_grant=GRANT)

    assert await credits.balance(pool, user_id) == 0


class _CountingConn:
    """A pool that records how many statements pass through it."""

    def __init__(self, inner: asyncpg.Pool) -> None:
        self._inner = inner
        self.statements: list[str] = []

    async def fetchval(self, sql: str, *args):
        self.statements.append(sql)
        return await self._inner.fetchval(sql, *args)

    async def execute(self, sql: str, *args):
        self.statements.append(sql)
        return await self._inner.execute(sql, *args)


async def test_the_account_and_its_credits_land_in_one_statement(pool):
    """The invariant, stated rather than timed.

    Against a pool every statement is its own transaction, so "two
    statements" and "a window where the account exists without its
    credits" are the same sentence. Asserting the count is what makes the
    guarantee independent of how fast anyone's socket is.
    """
    counting = _CountingConn(pool)

    await users.ensure_user(counting, str(uuid.uuid4()), "atomic@test.local", signup_grant=GRANT)

    assert len(counting.statements) == 1, (
        f"ensure_user issued {len(counting.statements)} statements; against a pool "
        "that is two transactions, and a sibling request can land between them"
    )
    sql = counting.statements[0]
    assert "app_users" in sql and "credit_entries" in sql
