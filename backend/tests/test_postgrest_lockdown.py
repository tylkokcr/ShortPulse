"""That the publishable key cannot read the database.

Supabase puts PostgREST in front of the `public` schema and serves it to
anyone holding the browser's publishable key. Migration 0007 shuts that
off; this file is the reason it stays off, because nothing else can show
it. The application connects as the owning role, which is exempt from
every restriction under test here — so the app works identically whether
0007 ran or not, the test suite was green while the hole was open, and
the only signal that ever arrived was an email from the vendor.

The local test database is plain Postgres with no `anon` role, which is
also every self-hoster's database. So each test builds the Supabase shape
it needs — the roles, and the grants Supabase's ALTER DEFAULT PRIVILEGES
would have applied — and then asks the question a stranger with the
publishable key would ask.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.services import db

TEST_DSN = os.environ.get(
    "SHORTPULSE_TEST_DATABASE_URL",
    "postgresql://postgres:shortpulse@localhost:55432/shortpulse",
)

# The four the vendor's email named, all of which hold something that
# should never be world-readable: addresses, the money ledger, what
# people typed, and what they thought of the result.
EXPOSED_TABLES = ("app_users", "projects", "credit_entries", "feedback")


@pytest.fixture
async def supabase_shaped():
    """A database wearing Supabase's roles and default grants.

    Created and dropped per test rather than left behind: these roles are
    the thing under test, and a leftover `anon` would make a later run of
    the *unfixed* migration pass for the wrong reason.
    """
    try:
        pool = await asyncpg.create_pool(TEST_DSN, min_size=1, max_size=4)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"no test Postgres at {TEST_DSN}: {exc}")

    async def drop_roles() -> None:
        for role in ("anon", "authenticated"):
            await pool.execute(f"drop owned by {role} cascade")
            await pool.execute(f"drop role {role}")

    try:
        for role in ("anon", "authenticated"):
            await pool.execute(
                f"do $$ begin if not exists (select 1 from pg_roles "
                f"where rolname = '{role}') then create role {role} nologin; end if; end $$"
            )
    except asyncpg.InsufficientPrivilegeError:
        await pool.close()
        pytest.skip("creating roles needs a superuser test database")

    # What Supabase's ALTER DEFAULT PRIVILEGES would have done on its own,
    # restored rather than assumed.
    #
    # The test database is long-lived and 0007's REVOKE persists in it, so
    # a fixture that only granted tables would hand later runs a database
    # already locked down by an earlier run — and every assertion below
    # would pass without the migration under test doing anything. Two of
    # them did exactly that before this was written.
    #
    # Sequences are listed for the same reason in miniature: without them
    # an INSERT fails on `credit_entries_id_seq` instead of on the table,
    # which looks identical from the outside and proves nothing.
    await pool.execute("grant usage on schema public to anon, authenticated")
    await pool.execute("grant all on all tables in schema public to anon, authenticated")
    await pool.execute("grant all on all sequences in schema public to anon, authenticated")
    await pool.execute(
        "grant execute on all functions in schema public to public, anon, authenticated"
    )
    # And RLS back off, for the same reason: `enable row level security`
    # persists too, so without this every test here would be measuring the
    # previous run instead of this one.
    for row in await pool.fetch(
        """select c.relname from pg_class c
           join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'public' and c.relkind = 'r'
             and pg_get_userbyid(c.relowner) = current_user"""
    ):
        await pool.execute(f"alter table {row['relname']} disable row level security")

    yield pool

    try:
        await drop_roles()
    finally:
        await pool.close()


async def _as_anon(pool: asyncpg.Pool, sql: str):
    """Run one statement with the privileges the publishable key carries.

    `set local role` inside an aborted-on-exit transaction is the closest
    thing to holding that key without holding it: PostgREST authenticates
    as itself and then does exactly this.
    """
    async with pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            await conn.execute("set local role anon")
            return await conn.fetch(sql)
        finally:
            await tx.rollback()


@pytest.mark.parametrize("table", EXPOSED_TABLES)
async def test_the_browser_key_cannot_read_a_table(supabase_shaped, table):
    """The critical finding, one test per table named in the email."""
    await db.apply_migrations(supabase_shaped)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _as_anon(supabase_shaped, f"select * from {table} limit 1")


async def test_the_browser_key_cannot_write_the_ledger(supabase_shaped):
    """Reading addresses is the embarrassment; writing this table is the
    one that costs money. Balances are sum(delta) over these rows, so an
    INSERT anyone can make is a credit anyone can mint.

    Against a real account rather than a random uuid, which matters more
    than it looks: an invented user_id fails the foreign key before
    Postgres ever checks privileges, so the first version of this test
    raised — and passed — with the hole standing wide open.
    """
    user_id = await supabase_shaped.fetchval(
        "insert into app_users (email) values ($1) returning id",
        f"{uuid.uuid4()}@lockdown.test",
    )
    await db.apply_migrations(supabase_shaped)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _as_anon(
            supabase_shaped,
            "insert into credit_entries (user_id, delta, reason) "
            f"values ('{user_id}', 1000, 'purchase') returning id",
        )


async def test_the_browser_key_cannot_call_refund_project(supabase_shaped):
    """The half the vendor's linter did not rate critical.

    PostgREST publishes a public function as /rest/v1/rpc/<name> to anyone
    who may execute it, and Postgres grants EXECUTE to PUBLIC by default.
    refund_project appends *positive* ledger rows, so it was an
    unauthenticated write with a payout attached.
    """
    await db.apply_migrations(supabase_shaped)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _as_anon(supabase_shaped, f"select refund_project('{uuid.uuid4()}')")


async def test_rls_is_on_everywhere_it_can_be_seen(supabase_shaped):
    """Belt and braces, asserted separately from the grants.

    A later migration that grants a table back — or a hand-run GRANT in
    the dashboard — must still find RLS underneath it, and this is the
    only test that fails if 0007's loop ever stops covering a new table.
    """
    await db.apply_migrations(supabase_shaped)

    rows = await supabase_shaped.fetch(
        """
        select c.relname, c.relrowsecurity
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r'
          and pg_get_userbyid(c.relowner) = current_user
        """
    )
    assert rows, "no owned tables found — the query is wrong, not the schema"
    assert [r["relname"] for r in rows if not r["relrowsecurity"]] == []


async def test_the_application_still_owns_its_data(supabase_shaped):
    """The whole risk of this change, in one test.

    RLS with no policies denies everything, and the only reason the app
    survives it is that Postgres exempts a table's owner unless FORCE ROW
    LEVEL SECURITY is set. If someone ever adds `force`, every test above
    keeps passing and the product stops working — this is the one that
    catches it.
    """
    await db.apply_migrations(supabase_shaped)

    user_id = await supabase_shaped.fetchval(
        "insert into app_users (email) values ($1) returning id",
        f"{uuid.uuid4()}@lockdown.test",
    )
    await supabase_shaped.execute(
        "insert into credit_entries (user_id, delta, reason) values ($1, 5, 'grant')",
        user_id,
    )

    assert await supabase_shaped.fetchval("select credit_balance($1)", user_id) == 5
    assert await supabase_shaped.fetchval(
        "select count(*) from app_users where id = $1", user_id
    ) == 1
