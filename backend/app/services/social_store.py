"""Reading and writing connections and posts.

The one rule this module exists to enforce: tokens are decrypted on the
publish path and nowhere else. `list_connections` is what the UI calls and
it cannot return a token even by accident — the column is not in its
select. `load_for_publish` is the only function that decrypts, and it is
called by the publish manager.

Splitting them costs one extra query on a path that runs twice a day. It
buys the guarantee that a bug in the connections screen cannot serialise
somebody's YouTube credentials into an HTTP response.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from app.services.social.base import OAuthTokens, PlatformAccount
from app.services.social_tokens import TokenCipher

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Connection:
    """A connected account, as the UI sees it — no tokens."""

    id: str
    platform: str
    external_account_id: str
    display_name: str | None
    auto_publish: bool
    # Null until something has actually been published through it. The
    # publish manager reads this to decide whether an automatic post is
    # held for review; see 0008 for why that rule exists.
    first_post_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class ConnectionWithTokens:
    id: str
    platform: str
    user_id: str
    tokens: OAuthTokens
    first_post_at: datetime | None


async def upsert_connection(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    platform: str,
    account: PlatformAccount,
    tokens: OAuthTokens,
    cipher: TokenCipher,
) -> str:
    """Store a fresh grant, replacing any previous one for this account.

    Reconnecting is the documented fix for half the ways a connection can
    break, so it has to land on the existing row rather than fail on the
    unique key — and it has to clear `revoked_at`, or a user who
    disconnected and changed their mind would reconnect into a row nothing
    reads.

    `first_post_at` is deliberately *not* cleared. Reconnecting the same
    account is not the same as connecting a new one: the pipe has been
    proven before, and making someone re-approve a first post because
    their token expired would be a rule protecting nothing.
    """
    row = await pool.fetchrow(
        """
        insert into social_connections (
            user_id, platform, external_account_id, display_name,
            access_token_enc, refresh_token_enc, access_expires_at, scopes
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8)
        on conflict (user_id, platform, external_account_id) do update set
            display_name      = excluded.display_name,
            access_token_enc  = excluded.access_token_enc,
            refresh_token_enc = coalesce(excluded.refresh_token_enc,
                                         social_connections.refresh_token_enc),
            access_expires_at = excluded.access_expires_at,
            scopes            = excluded.scopes,
            revoked_at        = null,
            updated_at        = now()
        returning id
        """,
        user_id,
        platform,
        account.external_id,
        account.display_name,
        cipher.encrypt(tokens.access_token),
        cipher.encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        tokens.expires_at,
        tokens.scopes,
    )
    return str(row["id"])


async def list_connections(pool: asyncpg.Pool, user_id: str) -> list[Connection]:
    """Live connections for this user. Never selects a token column."""
    rows = await pool.fetch(
        """
        select id, platform, external_account_id, display_name,
               auto_publish, first_post_at, created_at
        from social_connections
        where user_id = $1 and revoked_at is null
        order by created_at
        """,
        user_id,
    )
    return [
        Connection(
            id=str(r["id"]),
            platform=r["platform"],
            external_account_id=r["external_account_id"],
            display_name=r["display_name"],
            auto_publish=r["auto_publish"],
            first_post_at=r["first_post_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


async def load_for_publish(
    pool: asyncpg.Pool, connection_id: str, cipher: TokenCipher
) -> ConnectionWithTokens | None:
    """The only function that decrypts. Called by the publish manager."""
    row = await pool.fetchrow(
        """
        select id, platform, user_id, access_token_enc, refresh_token_enc,
               access_expires_at, scopes, first_post_at
        from social_connections
        where id = $1 and revoked_at is null
        """,
        connection_id,
    )
    if row is None:
        return None

    return ConnectionWithTokens(
        id=str(row["id"]),
        platform=row["platform"],
        user_id=str(row["user_id"]),
        tokens=OAuthTokens(
            access_token=cipher.decrypt(row["access_token_enc"]) or "",
            refresh_token=cipher.decrypt(row["refresh_token_enc"]),
            expires_at=row["access_expires_at"],
            scopes=list(row["scopes"] or []),
        ),
        first_post_at=row["first_post_at"],
    )


async def store_refreshed_tokens(
    pool: asyncpg.Pool, connection_id: str, tokens: OAuthTokens, cipher: TokenCipher
) -> None:
    await pool.execute(
        """
        update social_connections
           set access_token_enc = $2, access_expires_at = $3, updated_at = now()
         where id = $1
        """,
        connection_id,
        cipher.encrypt(tokens.access_token),
        tokens.expires_at,
    )


async def set_auto_publish(
    pool: asyncpg.Pool, connection_id: str, user_id: str, enabled: bool
) -> bool:
    """Returns whether a row was actually changed, so the caller can 404
    rather than silently accepting a toggle for somebody else's row."""
    result = await pool.execute(
        """
        update social_connections set auto_publish = $3, updated_at = now()
        where id = $1 and user_id = $2 and revoked_at is null
        """,
        connection_id,
        user_id,
        enabled,
    )
    return result.endswith(" 1")


async def revoke_connection(pool: asyncpg.Pool, connection_id: str, user_id: str) -> bool:
    """Disconnect. The row stays so published posts keep a parent."""
    result = await pool.execute(
        """
        update social_connections
           set revoked_at = now(), updated_at = now(),
               access_token_enc = ''::bytea, refresh_token_enc = null
         where id = $1 and user_id = $2 and revoked_at is null
        """,
        connection_id,
        user_id,
    )
    return result.endswith(" 1")


async def mark_first_post(pool: asyncpg.Pool, connection_id: str) -> None:
    """Records that this connection has now published something.

    `coalesce` rather than an unconditional set: this runs after every
    successful post, and the column means "when the first one went out".
    """
    await pool.execute(
        """
        update social_connections
           set first_post_at = coalesce(first_post_at, now()), updated_at = now()
         where id = $1
        """,
        connection_id,
    )


# --------------------------------------------------------------------------
# Posts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Post:
    id: str
    project_id: str
    connection_id: str
    platform: str
    status: str
    title: str | None
    description: str | None
    hashtags: list[str]
    privacy: str
    platform_url: str | None
    error: str | None
    created_at: datetime
    published_at: datetime | None


_POST_COLUMNS = """
    p.id, p.project_id, p.connection_id, c.platform, p.status, p.title,
    p.description, p.hashtags, p.privacy, p.platform_url, p.error,
    p.created_at, p.published_at
"""


def _to_post(row: asyncpg.Record) -> Post:
    return Post(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        connection_id=str(row["connection_id"]),
        platform=row["platform"],
        status=row["status"],
        title=row["title"],
        description=row["description"],
        hashtags=list(row["hashtags"] or []),
        privacy=row["privacy"],
        platform_url=row["platform_url"],
        error=row["error"],
        created_at=row["created_at"],
        published_at=row["published_at"],
    )


async def create_post(
    pool: asyncpg.Pool,
    *,
    project_id: str,
    connection_id: str,
    user_id: str,
    title: str,
    description: str,
    hashtags: list[str],
    privacy: str,
    status: str,
) -> str | None:
    """Record an intent to publish.

    Returns None when this project has already been published to this
    connection — the partial unique index in 0008 makes that a conflict
    rather than a second video on somebody's channel. The caller turns it
    into "already posted" rather than an error, because from the user's
    side that is exactly what it is.
    """
    row = await pool.fetchrow(
        """
        insert into social_posts (
            project_id, connection_id, user_id, title, description,
            hashtags, privacy, status
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8)
        on conflict do nothing
        returning id
        """,
        project_id,
        connection_id,
        user_id,
        title,
        description,
        hashtags,
        privacy,
        status,
    )
    return str(row["id"]) if row else None


async def list_posts_for_project(pool: asyncpg.Pool, project_id: str, user_id: str) -> list[Post]:
    rows = await pool.fetch(
        f"""
        select {_POST_COLUMNS}
        from social_posts p
        join social_connections c on c.id = p.connection_id
        where p.project_id = $1 and p.user_id = $2
        order by p.created_at
        """,
        project_id,
        user_id,
    )
    return [_to_post(r) for r in rows]


async def get_post(pool: asyncpg.Pool, post_id: str) -> Post | None:
    row = await pool.fetchrow(
        f"""
        select {_POST_COLUMNS}
        from social_posts p
        join social_connections c on c.id = p.connection_id
        where p.id = $1
        """,
        post_id,
    )
    return _to_post(row) if row else None


async def mark_uploading(pool: asyncpg.Pool, post_id: str) -> None:
    await pool.execute(
        """
        update social_posts
           set status = 'uploading', attempts = attempts + 1, updated_at = now()
         where id = $1
        """,
        post_id,
    )


async def mark_published(
    pool: asyncpg.Pool, post_id: str, *, platform_post_id: str, url: str | None, privacy: str
) -> None:
    await pool.execute(
        """
        update social_posts
           set status = 'published', platform_post_id = $2, platform_url = $3,
               privacy = $4, error = null, published_at = now(), updated_at = now()
         where id = $1
        """,
        post_id,
        platform_post_id,
        url,
        privacy,
    )


async def mark_failed(pool: asyncpg.Pool, post_id: str, error: str) -> None:
    await pool.execute(
        """
        update social_posts
           set status = 'failed', error = $2, updated_at = now()
         where id = $1
        """,
        post_id,
        # The column feeds straight into the UI, so it holds the sentence
        # the user reads. Truncated rather than left unbounded because an
        # upstream error body can be a page of HTML.
        error[:500],
    )


async def approve_post(pool: asyncpg.Pool, post_id: str, user_id: str) -> bool:
    """Release a post that was held for review onto the queue."""
    result = await pool.execute(
        """
        update social_posts set status = 'queued', updated_at = now()
         where id = $1 and user_id = $2 and status = 'awaiting_review'
        """,
        post_id,
        user_id,
    )
    return result.endswith(" 1")


async def reclaim_interrupted(pool: asyncpg.Pool) -> list[str]:
    """Posts a worker was holding when the process died.

    'uploading' is the dangerous state: the platform may already have the
    bytes, so blindly requeueing risks a duplicate. But the partial unique
    index only stops a *second published row*, not a second video, and
    there is no way from here to ask YouTube "did you get one from me".

    So these are failed rather than retried, with a message that says what
    to check. Losing a post the user can repeat by pressing a button beats
    silently putting the same video on their channel twice.
    """
    rows = await pool.fetch(
        """
        update social_posts
           set status = 'failed',
               error = 'Interrupted while uploading. Check the platform before retrying — '
                       'it may have gone out.',
               updated_at = now()
         where status = 'uploading'
        returning id
        """
    )
    return [str(r["id"]) for r in rows]


async def queued_post_ids(pool: asyncpg.Pool) -> list[str]:
    """Everything waiting for a worker, oldest first. Read at startup to
    refill the in-memory queue, which is where the actual ordering lives
    while the process is alive."""
    rows = await pool.fetch(
        "select id from social_posts where status = 'queued' order by created_at"
    )
    return [str(r["id"]) for r in rows]
