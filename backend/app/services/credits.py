"""Credit ledger.

Balances are never stored — they are always `sum(delta)` over an
append-only table (see migrations/0001). The atomicity that stops a user
spending the same credit twice lives in the `spend_credits` SQL function,
not here; this module is a typed wrapper over it plus the pricing rules.

Rules worth keeping in mind when extending this:
  * Never UPDATE or DELETE a ledger row. Correct mistakes by appending a
    compensating entry so the history stays auditable.
  * Every debit that can be retried needs an idempotency key.
  * A refund is tied to a project and can only ever happen once.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg

from app.schemas.project import ProjectConfig, ProjectSource, VideoLength, VisualMode

logger = logging.getLogger(__name__)

# Postgres SQLSTATEs raised deliberately by spend_credits().
_INSUFFICIENT = "42501"  # insufficient_privilege, reused for "not enough credits"


class InsufficientCredits(Exception):
    """Raised when a user's balance cannot cover a render."""

    def __init__(self, balance: int, required: int) -> None:
        super().__init__(f"insufficient credits: balance {balance} < required {required}")
        self.balance = balance
        self.required = required


# ---------------------------------------------------------------------
# Pricing
#
# Cost is driven by what actually consumes machine time. Measured on this
# hardware (see any project's timings.json): image generation is ~84% of a
# fast_hybrid render, while stock_media skips that stage entirely and costs
# roughly a sixth as much wall clock. Longer presets mean more scenes,
# which scales close to linearly.
# ---------------------------------------------------------------------
_MODE_COST = {
    VisualMode.STOCK_MEDIA: 1,
    VisualMode.FAST_HYBRID: 3,
    VisualMode.AI_VIDEO: 10,
}

_LENGTH_MULTIPLIER = {
    VideoLength.SHORT: 1,
    VideoLength.MEDIUM: 2,
    VideoLength.LONG: 3,
}


# Captioning an upload skips script, voice and visuals entirely — the only
# real cost is one Whisper pass and one ffmpeg pass. It isn't free, because
# transcription is genuinely CPU-bound (a few seconds per minute of video),
# but it is the cheapest thing the product does.
AUTOCAPTION_COST = 1


def cost_for(config: ProjectConfig) -> int:
    """Credits a render of this shape costs. Deterministic: the caller is
    quoted this before the render starts and charged exactly this."""
    if config.source == ProjectSource.UPLOAD:
        return AUTOCAPTION_COST
    mode = VisualMode(config.visual_mode)
    length = VideoLength(config.video_length)
    return _MODE_COST[mode] * _LENGTH_MULTIPLIER[length]


@dataclass(frozen=True)
class CreditPack:
    """A one-off purchase of credits.

    Deliberately not a subscription: the pitch against the $20-50/month
    incumbents is that you pay for renders you actually run, so nothing
    here renews and nothing expires. Prices are in minor units (cents) to
    keep them integers all the way to the payment processor.
    """

    id: str
    credits: int
    price_cents: int
    popular: bool = False

    @property
    def price_usd(self) -> float:
        return self.price_cents / 100


# The ledger has no expiry column and none of the code prunes it, so
# "credits never expire" below is a property of the schema, not a promise
# the UI is making on its own.
CREDIT_PACKS: tuple[CreditPack, ...] = (
    CreditPack(id="starter", credits=100, price_cents=900),
    CreditPack(id="creator", credits=400, price_cents=2900, popular=True),
    CreditPack(id="studio", credits=1200, price_cents=7900),
)


def pack_by_id(pack_id: str) -> CreditPack | None:
    return next((pack for pack in CREDIT_PACKS if pack.id == pack_id), None)


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    delta: int
    reason: str
    project_id: str | None
    note: str | None
    created_at: object


async def balance(conn: asyncpg.Connection | asyncpg.Pool, user_id: str) -> int:
    return await conn.fetchval("select credit_balance($1)", user_id)


async def grant(
    conn: asyncpg.Connection | asyncpg.Pool,
    user_id: str,
    amount: int,
    *,
    reason: str = "grant",
    idempotency_key: str | None = None,
    note: str | None = None,
) -> int:
    """Add credits (signup bonus, purchase, manual adjustment).

    Returns the balance afterwards. With an idempotency key, replaying the
    same grant is a no-op — which is what makes a Stripe webhook safe to
    deliver more than once.
    """
    if amount <= 0:
        raise ValueError(f"grant amount must be positive, got {amount}")

    await conn.execute(
        """
        insert into credit_entries (user_id, delta, reason, idempotency_key, note)
        values ($1, $2, $3, $4, $5)
        on conflict (user_id, idempotency_key) where idempotency_key is not null
        do nothing
        """,
        user_id,
        amount,
        reason,
        idempotency_key,
        note,
    )
    return await balance(conn, user_id)


async def spend(
    conn: asyncpg.Connection | asyncpg.Pool,
    user_id: str,
    amount: int,
    *,
    project_id: str | None = None,
    idempotency_key: str | None = None,
    note: str | None = None,
) -> int:
    """Debit credits atomically. Returns the balance afterwards.

    Raises InsufficientCredits rather than letting the balance go negative.
    Concurrent debits for the same user serialize inside the SQL function;
    different users are unaffected.
    """
    try:
        return await conn.fetchval(
            "select spend_credits($1, $2, $3, $4, $5)",
            user_id,
            amount,
            project_id,
            idempotency_key,
            note,
        )
    except asyncpg.PostgresError as exc:
        if getattr(exc, "sqlstate", None) == _INSUFFICIENT:
            raise InsufficientCredits(await balance(conn, user_id), amount) from exc
        raise


async def refund_project(
    conn: asyncpg.Connection | asyncpg.Pool,
    project_id: str,
    *,
    note: str | None = None,
) -> int:
    """Return whatever a project was charged, at most once.

    Idempotent by design so the render-failure path and any reconciler can
    both call it without coordinating. Returns credits actually refunded
    (0 if the project was never charged, or was already refunded).
    """
    refunded = await conn.fetchval("select refund_project($1, $2)", project_id, note)
    if refunded:
        logger.info("Refunded %d credits for project %s", refunded, project_id)
    return refunded or 0


async def history(
    conn: asyncpg.Connection | asyncpg.Pool, user_id: str, limit: int = 50
) -> list[LedgerEntry]:
    rows = await conn.fetch(
        """
        select id, delta, reason, project_id, note, created_at
        from credit_entries
        where user_id = $1
        order by created_at desc, id desc
        limit $2
        """,
        user_id,
        limit,
    )
    return [
        LedgerEntry(
            id=r["id"],
            delta=r["delta"],
            reason=r["reason"],
            project_id=str(r["project_id"]) if r["project_id"] else None,
            note=r["note"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
