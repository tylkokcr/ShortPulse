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

# A dub is the autocaption pass plus a translation call and one synthesis
# per sentence — more work than captions, and still nothing beside a
# generated render, which pays for images. Two rather than one because the
# syntheses are the slowest part of the whole upload path, and one credit
# would price a five-minute job the same as a thirty-second one.
DUB_COST = 2


# Re-rolling one scene's visual on a finished video.
#
# Not derived from the render's price, because the work isn't a fraction
# of a render. It is one hosted image generation — a fraction of a cent —
# plus a full re-encode of the whole video, since finalize_render burns
# captions and mixes music over the entire timeline whatever changed. The
# re-encode dominates and it costs the same on a stock scene as on a
# generated one, which is why this is a flat price rather than a per-mode
# one.
REGENERATE_SCENE_COST = 1


def cost_for(config: ProjectConfig) -> int:
    """Credits a render of this shape costs. Deterministic: the caller is
    quoted this before the render starts and charged exactly this."""
    if config.source == ProjectSource.UPLOAD:
        return DUB_COST if config.dub_language else AUTOCAPTION_COST
    mode = VisualMode(config.visual_mode)
    length = VideoLength(config.video_length)
    return _MODE_COST[mode] * _LENGTH_MULTIPLIER[length]


# ---------------------------------------------------------------------
# What the signup grant buys
#
# The grant exists so someone can judge the output before paying, which
# stock_media does: its marginal cost to us is a Pexels search and an
# OpenAI call worth a fraction of a cent. fast_hybrid bills Replicate per
# scene — a signup's worth of it is real money leaving the account with
# nothing coming back — and ai_video wants a GPU we don't rent. So both
# sit behind a purchase rather than behind the grant.
#
# A pricing rule, deliberately here and not in visual_engine: that module
# answers what this machine *can* render, this answers what an account has
# *paid* to render. Keeping them apart is what lets an unavailable mode
# still report the operator-facing reason instead of an upsell.
# ---------------------------------------------------------------------
FREE_TIER_MODES: frozenset[VisualMode] = frozenset({VisualMode.STOCK_MEDIA})

# One finished video in a paid mode, on the house.
#
# The grant covering only stock footage was right about cost and wrong
# about first impressions: a side-by-side of the same topic had the stock
# cut matching a caregiving clip to a line about attraction while the
# generated one held its subject across every scene. Someone trying this
# for the first time was being shown the weaker half and judging the
# product by it.
#
# One is enough to see the difference and cheap enough not to think about:
# roughly two cents of hosted generation, against an impression that
# decides whether they come back. The signup grant caps the rest by
# itself — 10 credits does not stretch far at three a render.
FREE_TRIAL_GENERATED_VIDEOS = 1

# Read by a customer in a disabled tile's tooltip, so it says what to do
# rather than what went wrong.
PURCHASE_REQUIRED_REASON = (
    "unlocked by any credit pack — your free AI-stills video has been made, "
    "and the signup credits cover stock-footage renders after that"
)

# The same wall, reached from the other side. Re-rolling is not part of
# the trial: the trial is one video, and needing a credit pack to fix a
# scene arrives exactly when someone has decided they want the scene
# fixed — which is a better moment to ask than any other.
REROLL_PURCHASE_REQUIRED_REASON = (
    "re-drawing a scene needs a credit pack — the free video is one render, "
    "not an editing session"
)


async def generated_videos_delivered(
    conn: asyncpg.Connection | asyncpg.Pool, user_id: str
) -> int:
    """Finished videos this account has in a mode the grant doesn't cover.

    Counts what was *delivered*, not what was attempted. A render that
    failed cost the user nothing — it was refunded — so consuming their
    one free trial on it would charge them for our outage in the only
    currency they had. Retrying until it works is the correct behaviour,
    and each attempt still spends grant credits, which is what bounds it.

    Reaches inside `config`, which migration 0001 introduced on the
    understanding that nothing would. Nothing indexes it either — the
    filter that matters is user_id, which projects_user_created_idx
    covers, and the JSON test only runs over one account's own rows.
    """
    return await conn.fetchval(
        """
        select count(*) from projects
        where user_id = $1 and status = 'complete'
          and coalesce(config->>'visual_mode', '') <> all($2::text[])
        """,
        user_id,
        [str(m) for m in FREE_TIER_MODES],
    )


async def may_render_paid_mode(
    conn: asyncpg.Connection | asyncpg.Pool, user_id: str
) -> bool:
    """Whether this account can start a render in a paid visual mode.

    Two ways through: having bought credits, or not having spent the free
    trial yet. Kept in one function so the availability endpoint, the
    render gate and anything added later cannot disagree about who is
    allowed what — the same reason visual_engine.unavailable_reason is one
    function.
    """
    if await has_purchased(conn, user_id):
        return True
    return await generated_videos_delivered(conn, user_id) < FREE_TRIAL_GENERATED_VIDEOS


async def has_purchased(conn: asyncpg.Connection | asyncpg.Pool, user_id: str) -> bool:
    """Whether this account has ever bought credits.

    Ever, not currently. Someone who bought a pack and spent all of it
    keeps the modes it unlocked — they paid once and the ledger is
    append-only, so the row proving it cannot be spent away. Anything
    tied to the *balance* instead would re-lock a paying customer the
    moment they ran out, which is the worst possible moment to do it.
    """
    return await conn.fetchval(
        "select exists (select 1 from credit_entries where user_id = $1 and reason = 'purchase')",
        user_id,
    )


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
    reason: str = "render",
) -> int:
    """Debit credits atomically. Returns the balance afterwards.

    Raises InsufficientCredits rather than letting the balance go negative.
    Concurrent debits for the same user serialize inside the SQL function;
    different users are unaffected.

    `reason` decides what a later refund gives back, not just how the row
    reads: refund_project pays back every `render` row for a project, so a
    charge filed under that name is part of the render's price. Anything
    bought separately after the render — a scene re-roll — must say so or
    a refund hands it back too. See migrations/0005.
    """
    try:
        return await conn.fetchval(
            "select spend_credits($1, $2, $3, $4, $5, $6)",
            user_id,
            amount,
            project_id,
            idempotency_key,
            note,
            reason,
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


async def correct_charge(
    conn: asyncpg.Connection | asyncpg.Pool,
    project_id: str,
    amount: int,
    *,
    note: str | None = None,
) -> int:
    """Lower what a render is charged, after the fact.

    For a render that quietly delivered less than was bought — the paid-for
    visual mode failed and the pipeline fell back to stock footage. The
    video is real, so this is a price correction, not a refund.

    Written as a positive entry under reason 'render' rather than a
    'refund', and that distinction is load-bearing twice over:

      * `refund_project` sums the *render* entries to decide what a failed
        render owes back. A correction under this reason nets against the
        original charge, so a later failure returns what is actually still
        held rather than the full original price.
      * At most one 'refund' row per project exists by unique index. Taking
        that slot here would make a genuine failure refund silently return
        nothing.

    Idempotent per project, so a retried pipeline cannot pay it twice.
    """
    if amount <= 0:
        raise ValueError(f"correction must be positive, got {amount}")

    user_id = await conn.fetchval("select user_id from projects where id = $1", project_id)
    if user_id is None:
        return 0

    await conn.execute(
        """
        insert into credit_entries
            (user_id, delta, reason, project_id, idempotency_key, note)
        values ($1, $2, 'render', $3, $4, $5)
        on conflict (user_id, idempotency_key) where idempotency_key is not null
        do nothing
        """,
        user_id,
        amount,
        project_id,
        f"correction:{project_id}",
        note,
    )
    logger.info("Corrected the charge for project %s by +%d credits", project_id, amount)
    return amount


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
