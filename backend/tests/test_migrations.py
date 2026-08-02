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
