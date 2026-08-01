"""Postgres connection pool and migration runner.

Targets Supabase in production and a plain Postgres container in
development; the SQL in migrations/ is written to run unchanged on both.
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_pool: asyncpg.Pool | None = None


async def connect(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """Open the shared pool. Safe to call once at application startup."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        logger.info("Postgres pool opened")
    return _pool


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Postgres pool closed")


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised; call connect() first")
    return _pool


def optional_pool() -> asyncpg.Pool | None:
    """The pool if one is configured, else None.

    For code that has to work in both shapes of the product — a
    self-hosted install has no database and that is not an error.
    """
    return _pool


async def apply_migrations(target: asyncpg.Pool | asyncpg.Connection | None = None) -> list[str]:
    """Apply every .sql file in migrations/ in filename order.

    Each file is expected to be idempotent (`create ... if not exists`,
    `create or replace`), so re-running is harmless and no migration-state
    table is needed at this size. Revisit if migrations start needing
    destructive changes.
    """
    conn_source = target or pool()
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied: list[str] = []

    async def _run(conn: asyncpg.Connection) -> None:
        for path in files:
            logger.info("Applying migration %s", path.name)
            await conn.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)

    if isinstance(conn_source, asyncpg.Connection):
        await _run(conn_source)
    else:
        async with conn_source.acquire() as conn:
            await _run(conn)

    return applied
