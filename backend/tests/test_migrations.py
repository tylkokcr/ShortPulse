"""Migrations, applied to a scratch database.

These run against a database created from nothing, which is the only way to
test a migration honestly. The shared test database has every migration
already applied, and the fixtures re-apply them before each module — so a
test there cannot tell whether a migration exists or was reverted, it just
observes the end state.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

from app.services import db

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)


def _dsn_for(database: str) -> str:
    parts = urlsplit(TEST_DSN)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


@pytest.fixture
async def scratch_db():
    """An empty database, dropped afterwards."""
    name = f"shortpulse_mig_{uuid.uuid4().hex[:12]}"
    try:
        admin = await asyncpg.connect(_dsn_for("postgres"))
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres: {exc}")

    await admin.execute(f'create database "{name}"')
    conn = await asyncpg.connect(_dsn_for(name))
    try:
        yield conn
    finally:
        await conn.close()
        await admin.execute(f'drop database "{name}"')
        await admin.close()


async def _apply(conn: asyncpg.Connection, *filenames: str) -> None:
    for filename in filenames:
        sql = (db.MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
        await conn.execute(sql)


async def _insert_user(conn: asyncpg.Connection, email: str) -> None:
    await conn.execute(
        "insert into app_users (id, email) values ($1, $2) on conflict (id) do nothing",
        str(uuid.uuid4()),
        email,
    )


async def test_all_migrations_apply_to_an_empty_database(scratch_db):
    """A fresh install must come up with no manual steps."""
    applied = await db.apply_migrations(scratch_db)

    assert applied  # something actually ran
    assert await scratch_db.fetchval(
        "select count(*) from information_schema.tables "
        "where table_schema = 'public' and table_name in "
        "('app_users', 'projects', 'credit_entries')"
    ) == 3


async def test_migrations_are_idempotent(scratch_db):
    """apply_migrations runs every file on every startup — there is no
    migration-state table — so re-running must be a no-op rather than an
    error."""
    await db.apply_migrations(scratch_db)
    await db.apply_migrations(scratch_db)
    await db.apply_migrations(scratch_db)


async def test_0001_alone_locks_out_a_recycled_email(scratch_db):
    """Shows the problem 0002 exists to fix. Deleting a Supabase account
    and signing up again with the same address gives a new uuid and the
    same email; under 0001's `email text unique` that insert fails, and
    since it runs on every authenticated request the user is locked out
    entirely."""
    await _apply(scratch_db, "0001_projects_and_credits.sql")

    email = "recycled@example.test"
    await _insert_user(scratch_db, email)
    with pytest.raises(asyncpg.UniqueViolationError):
        await _insert_user(scratch_db, email)


async def test_0002_lets_a_recycled_email_through(scratch_db):
    await _apply(scratch_db, "0001_projects_and_credits.sql", "0002_relax_user_email.sql")

    email = "recycled@example.test"
    await _insert_user(scratch_db, email)
    await _insert_user(scratch_db, email)  # would raise before 0002

    assert await scratch_db.fetchval(
        "select count(*) from app_users where email = $1", email
    ) == 2


# --- 0005: a re-roll is not part of the render's price -------------------


async def _make_project(conn: asyncpg.Connection, user_id: str) -> str:
    project_id = str(uuid.uuid4())
    await conn.execute(
        "insert into projects (id, user_id, status, config) values ($1, $2, 'complete', $3)",
        project_id,
        user_id,
        "{}",
    )
    return project_id


async def _user(conn: asyncpg.Connection) -> str:
    user_id = str(uuid.uuid4())
    await conn.execute(
        "insert into app_users (id, email) values ($1, $2)",
        user_id,
        f"{user_id}@example.test",
    )
    return user_id


async def test_0001_alone_cannot_charge_for_anything_but_a_render(scratch_db):
    """Shows the problem 0005 exists to fix, from the other end: 0001's
    spend_credits takes five arguments and writes 'render' with no way to
    say otherwise."""
    await _apply(scratch_db, "0001_projects_and_credits.sql")

    with pytest.raises(asyncpg.PostgresError):
        await scratch_db.fetchval(
            "select spend_credits($1, $2, $3, $4, $5, $6)",
            str(uuid.uuid4()), 1, None, None, None, "regenerate",
        )


async def test_0005_keeps_a_re_roll_out_of_the_project_refund(scratch_db):
    """The invariant this whole feature is most likely to break.

    refund_project pays back every `render` row for a project. A scene
    re-roll is a separate purchase made after the render, so filing it
    under `render` would mean an unrelated refund also hands back every
    re-roll the customer bought and kept.
    """
    await db.apply_migrations(scratch_db)

    user_id = await _user(scratch_db)
    project_id = await _make_project(scratch_db, user_id)
    await scratch_db.execute(
        "insert into credit_entries (user_id, delta, reason) values ($1, 100, 'purchase')",
        user_id,
    )

    await scratch_db.fetchval(
        "select spend_credits($1, $2, $3, $4, $5, $6)",
        user_id, 9, project_id, f"render:{project_id}", None, "render",
    )
    await scratch_db.fetchval(
        "select spend_credits($1, $2, $3, $4, $5, $6)",
        user_id, 1, project_id, f"regen:{project_id}:3:1", None, "regenerate",
    )
    assert await scratch_db.fetchval("select credit_balance($1)", user_id) == 90

    refunded = await scratch_db.fetchval("select refund_project($1)", project_id)

    # The nine for the render, not the ten that left the account.
    assert refunded == 9
    assert await scratch_db.fetchval("select credit_balance($1)", user_id) == 99


async def test_0005_leaves_ordinary_render_charges_alone(scratch_db):
    """The defaulted parameter must not change what existing callers do —
    every current call site still passes five arguments."""
    await db.apply_migrations(scratch_db)

    user_id = await _user(scratch_db)
    project_id = await _make_project(scratch_db, user_id)
    await scratch_db.execute(
        "insert into credit_entries (user_id, delta, reason) values ($1, 50, 'purchase')",
        user_id,
    )

    await scratch_db.fetchval(
        "select spend_credits($1, $2, $3, $4, $5)",
        user_id, 3, project_id, f"render:{project_id}", None,
    )

    assert await scratch_db.fetchval(
        "select reason from credit_entries where idempotency_key = $1",
        f"render:{project_id}",
    ) == "render"
    assert await scratch_db.fetchval("select refund_project($1)", project_id) == 3
