"""Recording what came out wrong.

The privacy page promises no analytics, no tracking pixels and no
third-party scripts, and keeping that promise is worth more than anything
a vendor SDK would have reported. What it costs is knowing whether the
output is any good — so this asks, and keeps the answer in the same
database as everything else.

Deliberately about the render and not about the product. A star rating
averages to a number nobody can act on; "the fourth scene of a photoreal
fast_hybrid render was wrong, and it was the visual" changes what gets
built next. It is also collected exactly where the fix is: the row that
takes the complaint is the row with the re-roll button on it.

Self-hosted installs have no user and no pool, so nothing here runs there
— same rule as billing.
"""

from __future__ import annotations

import logging

import asyncpg
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# The countable half of the answer. Free text is kept too, but a fixed
# list is what makes "how often is it the visual" a query rather than a
# reading exercise.
REASONS = ("visual", "match", "voice", "captions", "pacing", "other")


class Feedback(BaseModel):
    """One verdict, on a scene or on the whole video."""

    scene_index: int | None = None
    rating: str
    reason: str | None = None
    note: str | None = Field(default=None, max_length=1000)


async def record(
    conn: asyncpg.Connection | asyncpg.Pool,
    *,
    project_id: str,
    user_id: str,
    entry: Feedback,
    visual_mode: str | None,
    art_style: str | None,
) -> None:
    """Save a verdict, replacing this person's previous one for that scene.

    An upsert rather than an append: someone who thumbs a scene down, re-rolls
    it and is then happy has changed their mind, not had two opinions. The
    partial unique indexes in migration 0006 are what the conflict targets,
    which is why the two cases are written separately — `scene_index is
    null` does not compare equal to itself.
    """
    if entry.scene_index is None:
        sql = """
            insert into feedback (project_id, user_id, scene_index, rating, reason, note,
                                  visual_mode, art_style)
            values ($1, $2, null, $3, $4, $5, $6, $7)
            on conflict (project_id, user_id) where scene_index is null
            do update set rating = excluded.rating, reason = excluded.reason,
                          note = excluded.note, updated_at = now()
        """
        args = (project_id, user_id, entry.rating, entry.reason, entry.note,
                visual_mode, art_style)
    else:
        sql = """
            insert into feedback (project_id, user_id, scene_index, rating, reason, note,
                                  visual_mode, art_style)
            values ($1, $2, $3, $4, $5, $6, $7, $8)
            on conflict (project_id, user_id, scene_index) where scene_index is not null
            do update set rating = excluded.rating, reason = excluded.reason,
                          note = excluded.note, updated_at = now()
        """
        args = (project_id, user_id, entry.scene_index, entry.rating, entry.reason,
                entry.note, visual_mode, art_style)

    await conn.execute(sql, *args)


async def for_project(
    conn: asyncpg.Connection | asyncpg.Pool, project_id: str, user_id: str
) -> list[Feedback]:
    """This person's verdicts on this project, so the UI can show them back.

    Scoped to the caller: feedback is a private note to us, not a review
    other people read.
    """
    rows = await conn.fetch(
        "select scene_index, rating, reason, note from feedback "
        "where project_id = $1 and user_id = $2",
        project_id,
        user_id,
    )
    return [Feedback(**dict(row)) for row in rows]
