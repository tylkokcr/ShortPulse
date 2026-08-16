"""Where people fall out, and whether what they got was any good.

The privacy page promises no analytics, no tracking pixels, no advertising
identifiers and no third-party scripts. That promise is worth keeping, and
it costs nothing here: every number below is derived from rows the product
already had to store to work at all — an account exists because someone
signed in, a project exists because someone asked for a render, a ledger
entry exists because money moved.

So this collects nothing. It reads.

    python scripts/funnel.py            # since launch
    python scripts/funnel.py --days 7   # a window

What it deliberately cannot tell you is how many people arrived and left
without signing up: nothing records a visit, and Caddy logs only warnings.
That number needs a decision about access logging rather than a script —
see the note at the end of the output.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services import db  # noqa: E402


def _pct(part: int, whole: int) -> str:
    """A rate, or a dash when the denominator makes it meaningless."""
    if whole <= 0:
        return "   —"
    return f"{100 * part / whole:5.1f}%"


def _bar(label: str, count: int, of: int, width: int = 24) -> str:
    filled = round(width * count / of) if of else 0
    return f"  {label:<22} {count:>5}  {_pct(count, of)}  {'█' * filled}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=0, help="only the last N days")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set — there is nothing to count.")
        return 1

    window = f"and {{}}.created_at > now() - interval '{args.days} days'" if args.days else ""
    pool = await db.connect(settings.database_url)
    try:
        signed_up = await pool.fetchval(
            f"select count(*) from app_users u where true {window.format('u')}"
        )
        # Activation is asking for a render, not finishing one: the gap
        # between these two is the pipeline failing or the user leaving
        # mid-wait, and they are different problems.
        started = await pool.fetchval(
            f"""select count(distinct p.user_id) from projects p
                where p.user_id is not null {window.format('p')}"""
        )
        completed = await pool.fetchval(
            f"""select count(distinct p.user_id) from projects p
                where p.user_id is not null and p.status = 'complete' {window.format('p')}"""
        )
        paid = await pool.fetchval(
            f"""select count(distinct c.user_id) from credit_entries c
                where c.reason = 'purchase' {window.format('c')}"""
        )
        revenue_credits = await pool.fetchval(
            f"""select coalesce(sum(c.delta), 0) from credit_entries c
                where c.reason = 'purchase' {window.format('c')}"""
        )

        renders = await pool.fetch(
            f"""select p.config->>'visual_mode' as mode, p.status, count(*) as n
                from projects p where true {window.format('p')}
                group by 1, 2 order by 3 desc"""
        )
        verdicts = await pool.fetch(
            f"""select f.rating, count(*) as n from feedback f
                where f.scene_index is null {window.format('f')} group by 1"""
        )
        complaints = await pool.fetch(
            f"""select f.reason, f.visual_mode, f.art_style, count(*) as n
                from feedback f
                where f.rating = 'down' and f.scene_index is not null {window.format('f')}
                group by 1, 2, 3 order by 4 desc limit 10"""
        )
    finally:
        await db.disconnect()

    scope = f"last {args.days} days" if args.days else "since launch"
    print(f"\nFunnel — {scope}\n")
    print(_bar("signed up", signed_up, signed_up))
    print(_bar("started a render", started, signed_up))
    print(_bar("got a finished video", completed, signed_up))
    print(_bar("bought credits", paid, signed_up))

    if signed_up and not started:
        print("\n  Nobody who signed up has started a render.")
        print("  That is an editor problem, not a marketing one.")
    elif started and not completed:
        print("\n  Renders are being started and none are finishing.")
        print("  Check the API logs before doing anything else.")
    elif completed and not paid:
        print("\n  People are finishing videos and not buying.")
        print("  Either the free grant is enough, or the price is wrong,")
        print("  or they were not happy with what they got — the verdicts below say which.")

    if renders:
        print("\nRenders by mode\n")
        for row in renders:
            print(f"  {str(row['mode'] or '?'):<14} {row['status']:<10} {row['n']:>4}")

    if verdicts:
        up = next((r["n"] for r in verdicts if r["rating"] == "up"), 0)
        down = next((r["n"] for r in verdicts if r["rating"] == "down"), 0)
        print(f"\nVerdicts on finished videos: {up} good, {down} bad  ({_pct(up, up + down)} good)")
    else:
        print("\nNo verdicts yet — nobody has answered 'how did this one come out?'.")

    if complaints:
        print("\nWhat people complain about\n")
        for row in complaints:
            print(
                f"  {str(row['reason']):<10} {str(row['visual_mode'] or '?'):<13}"
                f" {str(row['art_style'] or '?'):<12} {row['n']:>3}"
            )

    print(f"\nCredits bought: {revenue_credits}")
    print(
        "\nNot measured: how many people saw the landing page and left. Nothing\n"
        "records a visit and Caddy logs only warnings, so the top of this funnel\n"
        "is missing. Turning on Caddy's access log would supply it — and would\n"
        "start storing visitor IPs, which is a decision about the privacy page\n"
        "rather than a line of code.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
