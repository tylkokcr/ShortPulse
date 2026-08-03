"""Credit ledger tests, run against a real Postgres.

These deliberately do not mock the database. The whole correctness claim of
the ledger — that concurrent debits cannot overspend — lives in Postgres
locking semantics, and a mock would assert nothing about it.

Start a database with:

    docker run -d --name shortpulse-pg \
        -e POSTGRES_PASSWORD=shortpulse -e POSTGRES_DB=shortpulse \
        -p 55432:5432 postgres:17-alpine

Tests skip (rather than fail) when no database is reachable, so the rest of
the suite still runs on a machine without Docker.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest

from app.schemas.project import ProjectConfig, VideoLength, VisualMode
from app.services import credits, db

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)


@pytest.fixture(scope="module")
async def pool():
    try:
        p = await asyncpg.create_pool(TEST_DSN, min_size=1, max_size=12)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres at {TEST_DSN}: {exc}")
    await db.apply_migrations(p)
    yield p
    await p.close()


@pytest.fixture
async def user(pool):
    """A fresh user per test, so balances never bleed between tests."""
    user_id = await pool.fetchval(
        "insert into app_users (email) values ($1) returning id",
        f"{uuid.uuid4()}@test.local",
    )
    yield str(user_id)
    await pool.execute("delete from app_users where id = $1", user_id)


async def _project(pool, user_id: str, cost: int = 0) -> str:
    pid = uuid.uuid4()
    await pool.execute(
        """
        insert into projects (id, user_id, status, config, credits_cost)
        values ($1, $2, 'draft', '{}'::jsonb, $3)
        """,
        pid,
        uuid.UUID(user_id),
        cost,
    )
    return str(pid)


# --- balances and grants ------------------------------------------------


async def test_new_user_starts_at_zero(pool, user):
    assert await credits.balance(pool, user) == 0


async def test_grant_then_spend_moves_balance(pool, user):
    await credits.grant(pool, user, 10)
    assert await credits.balance(pool, user) == 10

    remaining = await credits.spend(pool, user, 3)
    assert remaining == 7
    assert await credits.balance(pool, user) == 7


async def test_grant_is_idempotent_under_the_same_key(pool, user):
    # A payment webhook delivered twice must not double-credit.
    for _ in range(3):
        await credits.grant(pool, user, 100, reason="purchase", idempotency_key="stripe_evt_1")
    assert await credits.balance(pool, user) == 100


async def test_spending_more_than_the_balance_is_refused(pool, user):
    await credits.grant(pool, user, 5)
    with pytest.raises(credits.InsufficientCredits):
        await credits.spend(pool, user, 6)
    assert await credits.balance(pool, user) == 5


async def test_spend_is_idempotent_under_the_same_key(pool, user):
    await credits.grant(pool, user, 10)
    first = await credits.spend(pool, user, 4, idempotency_key="render_1")
    second = await credits.spend(pool, user, 4, idempotency_key="render_1")
    assert first == second == 6
    assert await credits.balance(pool, user) == 6


# --- the property that actually matters ---------------------------------


async def test_debits_for_one_user_serialize(pool, user):
    """A second debit for the same user must wait for the first to commit.

    This is the load-bearing test for double-spend safety, and it asserts
    the serialization directly instead of hoping a race shows up: while one
    transaction holds the per-user advisory lock, a second debit is made to
    block, and is only allowed to proceed once the first commits.

    An earlier version of this test just fired N concurrent debits and
    checked the balance. That version passed even with the advisory lock
    removed — without an artificial delay the read-check-write window is
    microseconds wide, so the race almost never materialises and the test
    silently proved nothing.
    """
    await credits.grant(pool, user, 5)

    async with pool.acquire() as holder, pool.acquire() as waiter:
        tx = holder.transaction()
        await tx.start()
        # Takes the advisory lock and holds it for the open transaction.
        await credits.spend(holder, user, 1, idempotency_key="holder")

        # Let Postgres abort the blocked wait server-side (SQLSTATE 57014)
        # rather than cancelling from the client, which leaves the
        # connection in a state the pool can't safely reuse.
        await waiter.execute("set statement_timeout = '500ms'")
        with pytest.raises(asyncpg.QueryCanceledError):
            await credits.spend(waiter, user, 1, idempotency_key="waiter")
        await waiter.execute("set statement_timeout = 0")

        await tx.commit()

    # Only the first debit ever committed.
    assert await credits.balance(pool, user) == 4


async def test_debits_for_different_users_do_not_block_each_other(pool):
    """Locking is per user, so unrelated users must stay parallel.

    Guards against 'fixing' the race with a global lock, which would be
    correct but would serialize every customer behind every other.
    """
    ids = []
    for _ in range(4):
        uid = await pool.fetchval(
            "insert into app_users (email) values ($1) returning id",
            f"{uuid.uuid4()}@test.local",
        )
        ids.append(str(uid))
        await credits.grant(pool, str(uid), 1)

    async with pool.acquire() as holder:
        tx = holder.transaction()
        await tx.start()
        await credits.spend(holder, ids[0], 1)  # holds ids[0]'s lock

        # Everyone else must get through while that lock is held.
        await asyncio.wait_for(
            asyncio.gather(*(credits.spend(pool, uid, 1) for uid in ids[1:])),
            timeout=5.0,
        )
        await tx.commit()

    for uid in ids:
        assert await credits.balance(pool, uid) == 0
        await pool.execute("delete from app_users where id = $1", uuid.UUID(uid))


async def test_parallel_debits_never_overspend(pool, user):
    """Smoke test: many concurrent debits, balance must not go negative.

    Weaker than the serialization test above (it can pass by luck), but it
    exercises the real concurrent path end to end.
    """
    await credits.grant(pool, user, 5)

    async def try_spend(n: int) -> bool:
        try:
            await credits.spend(pool, user, 1, idempotency_key=f"concurrent_{n}")
            return True
        except credits.InsufficientCredits:
            return False

    results = await asyncio.gather(*(try_spend(i) for i in range(20)))

    assert sum(results) == 5
    assert await credits.balance(pool, user) == 0


# --- refunds ------------------------------------------------------------


async def test_failed_render_is_refunded_once(pool, user):
    await credits.grant(pool, user, 10)
    project_id = await _project(pool, user, cost=3)
    await credits.spend(pool, user, 3, project_id=project_id)
    assert await credits.balance(pool, user) == 7

    assert await credits.refund_project(pool, project_id) == 3
    assert await credits.balance(pool, user) == 10

    # The failure handler and a reconciler may both call this.
    assert await credits.refund_project(pool, project_id) == 0
    assert await credits.balance(pool, user) == 10


async def test_concurrent_refunds_pay_out_once(pool, user):
    await credits.grant(pool, user, 10)
    project_id = await _project(pool, user, cost=4)
    await credits.spend(pool, user, 4, project_id=project_id)

    results = await asyncio.gather(
        *(credits.refund_project(pool, project_id) for _ in range(8))
    )

    assert sum(results) == 4, "a project must only ever be refunded once"
    assert await credits.balance(pool, user) == 10


async def test_refunding_an_uncharged_project_is_a_noop(pool, user):
    project_id = await _project(pool, user)
    assert await credits.refund_project(pool, project_id) == 0
    assert await credits.balance(pool, user) == 0


# --- pricing ------------------------------------------------------------


def test_cost_scales_with_mode_and_length():
    def cfg(mode: VisualMode, length: VideoLength) -> ProjectConfig:
        return ProjectConfig(topic="t", visual_mode=mode, video_length=length)

    stock_short = credits.cost_for(cfg(VisualMode.STOCK_MEDIA, VideoLength.SHORT))
    hybrid_short = credits.cost_for(cfg(VisualMode.FAST_HYBRID, VideoLength.SHORT))
    hybrid_long = credits.cost_for(cfg(VisualMode.FAST_HYBRID, VideoLength.LONG))
    ai_short = credits.cost_for(cfg(VisualMode.AI_VIDEO, VideoLength.SHORT))

    # Ordering follows measured compute: stock < hybrid < ai_video.
    assert stock_short < hybrid_short < ai_short
    # Longer presets render more scenes, so they cost more.
    assert hybrid_long > hybrid_short
    assert stock_short >= 1, "every render costs at least one credit"
