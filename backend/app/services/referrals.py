"""Invite a friend, get credits when they make their first video.

The signup grant is unconditional; this is the part that is earned. The
inviter is paid REWARD credits when an invited friend's first video
finishes, for up to CAP friends. Paying on the video rather than on the
signup is what keeps it from being a credit tap: the friend has to be
someone who used the product, not an address made for the purpose.

Database-only. A self-hosted install has no credits to give.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

import asyncpg

from app.services import credits

logger = logging.getLogger(__name__)

REWARD = 10
CAP = 5
# A link only counts for an account this new. Without it, anyone already
# signed up could hand their account to a friend's code after the fact.
CLAIM_WINDOW = timedelta(days=7)

# No 0/o, 1/l/i: read aloud or typed from a screenshot, they get confused.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_CODE_LEN = 8


def _new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))


def valid_code(code: str) -> bool:
    return len(code) == _CODE_LEN and all(c in _ALPHABET for c in code)


async def code_for(pool: asyncpg.Pool, user_id: str) -> str:
    """This account's code, made the first time it is asked for."""
    for _ in range(5):
        code = await pool.fetchval(
            """
            with made as (
                insert into referral_codes (user_id, code) values ($1, $2)
                on conflict do nothing
                returning code
            )
            select code from made
            union all
            select code from referral_codes where user_id = $1
            limit 1
            """,
            user_id,
            _new_code(),
        )
        if code:
            return str(code)
    raise RuntimeError("Could not make a referral code")  # pragma: no cover


async def claim(pool: asyncpg.Pool, user_id: str, code: str) -> bool:
    """Record that this account came through `code`. False, and nothing
    recorded, for an unknown code, the account's own, an account older
    than CLAIM_WINDOW, or one that already has an inviter."""
    if not valid_code(code):
        return False
    claimed = await pool.fetchval(
        """
        insert into referrals (referred_id, referrer_id)
        select u.id, c.user_id
          from app_users u, referral_codes c
         where u.id = $1
           and c.code = $2
           and c.user_id <> u.id
           and u.created_at > now() - $3::interval
        on conflict (referred_id) do nothing
        returning 1
        """,
        user_id,
        code,
        CLAIM_WINDOW,
    )
    if claimed:
        logger.info("User %s joined through referral code %s", user_id, code)
    return bool(claimed)


async def settle(pool: asyncpg.Pool, referred_id: str) -> int | None:
    """Called when one of this account's videos finishes. Pays the
    account's inviter, once, if they are still under CAP.

    Returns the credits paid (0 when over the cap), or None when there was
    nothing to settle. One transaction, with the inviter's row locked, so
    two friends finishing at the same moment cannot both be the fifth.
    """
    async with pool.acquire() as conn, conn.transaction():
        referrer = await conn.fetchval(
            "select referrer_id from referrals where referred_id = $1 and settled_at is null for update",
            referred_id,
        )
        if referrer is None:
            return None
        await conn.execute("select 1 from app_users where id = $1 for update", referrer)
        paid = await conn.fetchval(
            "select count(*) from referrals where referrer_id = $1 and rewarded", referrer
        )
        rewarded = paid < CAP
        if rewarded:
            await credits.grant(
                cast(asyncpg.Connection, conn),
                str(referrer),
                REWARD,
                reason="grant",
                idempotency_key=f"referral:{referred_id}",
                note="a friend you invited made their first video",
            )
        await conn.execute(
            "update referrals set settled_at = now(), rewarded = $2 where referred_id = $1",
            referred_id,
            rewarded,
        )
    logger.info("Referral of %s settled: %s", referred_id, "paid" if rewarded else "over the cap")
    return REWARD if rewarded else 0


@dataclass(frozen=True)
class Summary:
    code: str
    joined: int  # signed up through the link
    rewarded: int  # paid for
    reward: int = REWARD
    cap: int = CAP


async def summary(pool: asyncpg.Pool, user_id: str) -> Summary:
    code = await code_for(pool, user_id)
    row = await pool.fetchrow(
        """
        select count(*) as joined, count(*) filter (where rewarded) as rewarded
          from referrals where referrer_id = $1
        """,
        user_id,
    )
    if row is None:  # pragma: no cover - an aggregate always returns a row
        return Summary(code=code, joined=0, rewarded=0)
    return Summary(code=code, joined=int(row["joined"]), rewarded=int(row["rewarded"]))
