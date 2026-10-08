"""Invite a friend: who gets paid, when, and how often.

Against a real Postgres, like the ledger tests — the cap is enforced by
a locked count, and that is not something a fake can show."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import asyncpg
import pytest

from app.services import credits, referrals
from tests.test_credits import TEST_DSN


@pytest.fixture(scope="module")
async def pool():
    from app.services import db

    try:
        p = await asyncpg.create_pool(TEST_DSN, min_size=1, max_size=12)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres at {TEST_DSN}: {exc}")
    await db.apply_migrations(p)
    yield p
    await p.close()


@pytest.fixture
async def new_user(pool):
    made: list[str] = []

    async def make(age_days: int = 0) -> str:
        user_id = await pool.fetchval(
            "insert into app_users (email, created_at) values ($1, now() - $2::interval) returning id",
            f"{uuid.uuid4()}@test.local",
            timedelta(days=age_days),
        )
        made.append(str(user_id))
        return str(user_id)

    yield make
    await pool.execute("delete from app_users where id = any($1::uuid[])", made)


async def test_a_friend_is_paid_for_on_their_first_video_not_on_signup(pool, new_user):
    inviter, friend = await new_user(), await new_user()
    code = await referrals.code_for(pool, inviter)
    assert await referrals.claim(pool, friend, code)
    assert await credits.balance(pool, inviter) == 0

    assert await referrals.settle(pool, friend) == referrals.REWARD
    assert await credits.balance(pool, inviter) == referrals.REWARD
    # A second video pays nothing more.
    assert await referrals.settle(pool, friend) is None
    assert await credits.balance(pool, inviter) == referrals.REWARD


async def test_the_code_is_stable(pool, new_user):
    user = await new_user()
    assert await referrals.code_for(pool, user) == await referrals.code_for(pool, user)


async def test_no_paying_for_yourself_an_old_account_or_a_second_inviter(pool, new_user):
    inviter, other = await new_user(), await new_user()
    code = await referrals.code_for(pool, inviter)
    assert not await referrals.claim(pool, inviter, code)
    old = await new_user(age_days=30)
    assert not await referrals.claim(pool, old, code)
    friend = await new_user()
    assert await referrals.claim(pool, friend, code)
    assert not await referrals.claim(pool, friend, await referrals.code_for(pool, other))
    assert not await referrals.claim(pool, await new_user(), "nosuchco")
    assert not await referrals.claim(pool, await new_user(), "'; drop")


async def test_only_the_first_five_friends_are_paid_for_even_at_once(pool, new_user):
    inviter = await new_user()
    code = await referrals.code_for(pool, inviter)
    friends = [await new_user() for _ in range(referrals.CAP + 3)]
    for friend in friends:
        assert await referrals.claim(pool, friend, code)

    paid = await asyncio.gather(*(referrals.settle(pool, f) for f in friends))
    assert sorted(paid, reverse=True) == [referrals.REWARD] * referrals.CAP + [0] * 3
    assert await credits.balance(pool, inviter) == referrals.REWARD * referrals.CAP

    summary = await referrals.summary(pool, inviter)
    assert (summary.joined, summary.rewarded) == (referrals.CAP + 3, referrals.CAP)


async def test_only_a_finished_video_settles_and_a_failure_never_breaks_the_queue(monkeypatch):
    from types import SimpleNamespace

    from app.schemas.project import ProjectStatus
    from app.services import db, project_store, render_manager

    settled: list[str] = []
    status = {"p": ProjectStatus.FAILED}

    async def get_project(project_id):
        return SimpleNamespace(status=status["p"])

    async def owner_of(project_id):
        return "owner-1"

    async def settle(pool, owner):
        settled.append(owner)
        raise RuntimeError("ledger down")

    monkeypatch.setattr(db, "optional_pool", lambda: object())
    monkeypatch.setattr(project_store, "get_project", get_project)
    monkeypatch.setattr(project_store, "owner_of", owner_of)
    monkeypatch.setattr(referrals, "settle", settle)

    await render_manager._settle_referral("p")
    assert settled == []
    status["p"] = ProjectStatus.COMPLETE
    await render_manager._settle_referral("p")  # raises inside, must not escape
    assert settled == ["owner-1"]
