-- Publishing a finished render to the platforms it was made for.
--
-- Two tables: what a user has connected, and what we tried to post. The
-- split matters because a connection outlives any single post — a token
-- refreshed, a permission revoked, an account renamed — while a post is a
-- record of one attempt and never changes afterwards except to reach a
-- terminal state.

-- ---------------------------------------------------------------------
-- social_connections
--
-- One row per (user, platform, account on that platform). A user may
-- connect two YouTube channels, or the same platform from two accounts,
-- so the account id is part of the key rather than assumed unique.
--
-- The tokens are the most sensitive thing this database has ever held.
-- They are not credentials *for* ShortPulse, they are credentials for
-- somebody's TikTok, and a leak means a stranger posting as them. They
-- are stored encrypted (see services/social_tokens.py) so that reading
-- the table is not the same as holding the accounts, and the columns are
-- bytea rather than text to make it obvious at a glance that nothing
-- readable is meant to be in them.
-- ---------------------------------------------------------------------
create table if not exists social_connections (
    id                   uuid primary key default gen_random_uuid(),
    user_id              uuid not null references app_users(id) on delete cascade,
    platform             text not null
                         check (platform in ('youtube', 'instagram', 'tiktok')),

    -- How the platform identifies the account: a YouTube channel id, an
    -- Instagram business account id, a TikTok open id.
    external_account_id  text not null,
    -- For the UI, so a user picking between two connected channels sees
    -- names rather than ids. Refreshed opportunistically; never trusted
    -- for anything but display.
    display_name         text,

    access_token_enc     bytea not null,
    refresh_token_enc    bytea,
    access_expires_at    timestamptz,
    -- What the user actually granted. Recorded because a platform can
    -- return fewer scopes than were asked for, and the first sign of that
    -- should be a clear refusal at publish time rather than a 403 from
    -- the API halfway through an upload.
    scopes               text[] not null default '{}',

    -- Post without asking, once the render finishes.
    --
    -- Default false and it must stay that way. A user who has not opted
    -- in has not agreed to anything being published in their name, and
    -- every one of these platforms takes a dim view of applications that
    -- decide otherwise. It is per connection rather than per user because
    -- "automatic to my own YouTube, ask me before TikTok" is a reasonable
    -- thing to want.
    auto_publish         boolean not null default false,

    -- When something first went out through this connection.
    --
    -- Null means the pipe has never been proven. Until it is, an
    -- automatic post is held for review even with auto_publish on: the
    -- cost is one click, once, and it is what stands between a bad render
    -- and somebody's real audience.
    first_post_at        timestamptz,

    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    -- Set when the user disconnects, or when the platform tells us the
    -- grant is gone. The row is kept rather than deleted so that posts
    -- made through it keep a parent to point at.
    revoked_at           timestamptz
);

create unique index if not exists social_connections_account_idx
    on social_connections (user_id, platform, external_account_id);

-- The publish path asks "what live connections does this user have",
-- which is this index and nothing else.
create index if not exists social_connections_user_idx
    on social_connections (user_id) where revoked_at is null;

-- ---------------------------------------------------------------------
-- social_posts
--
-- One attempt to put one project on one connection.
--
-- `title` / `description` / `hashtags` are snapshotted rather than read
-- back from the project at publish time. The project's copy can be edited
-- afterwards, and a record of what was posted has to say what was posted
-- — not what the caption says today.
-- ---------------------------------------------------------------------
create table if not exists social_posts (
    id                uuid primary key default gen_random_uuid(),
    project_id        uuid not null references projects(id) on delete cascade,
    connection_id     uuid not null references social_connections(id) on delete cascade,
    user_id           uuid not null references app_users(id) on delete cascade,

    -- awaiting_review — auto_publish is on but this connection has never
    --                   posted, so a human still has to press the button
    -- queued          — waiting for a worker
    -- uploading       — a worker has it; the platform may already have
    --                   bytes, which is why this is distinct from queued
    -- published       — the platform accepted it and gave us an id
    -- failed          — terminal; `error` says why, in the user's words
    status            text not null default 'queued'
                      check (status in ('awaiting_review', 'queued', 'uploading',
                                        'published', 'failed')),

    title             text,
    description       text,
    hashtags          text[] not null default '{}',
    -- What visibility was asked for. Worth storing because it is not
    -- always what was wanted: an unaudited TikTok client can only post
    -- SELF_ONLY and an unverified YouTube project can only post private,
    -- so this column is how a user finds out why their "public" video
    -- isn't public.
    privacy           text not null default 'public',

    platform_post_id  text,
    platform_url      text,
    error             text,
    attempts          integer not null default 0,

    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    published_at      timestamptz
);

-- The same video, published twice to the same account, is the failure a
-- retry loop produces and nobody wants. Same shape as the one-refund-per-
-- project index in 0001: let the database make it impossible rather than
-- coordinating the callers.
create unique index if not exists social_posts_one_publish_idx
    on social_posts (project_id, connection_id)
    where status = 'published';

create index if not exists social_posts_user_idx
    on social_posts (user_id, created_at desc);

create index if not exists social_posts_project_idx
    on social_posts (project_id);

-- Anything a worker was holding when the process died. Same problem the
-- render reconciler solves, and found the same way.
create index if not exists social_posts_pending_idx
    on social_posts (status) where status in ('queued', 'uploading');

-- ---------------------------------------------------------------------
-- Lock these two down here, rather than leaving it to 0007
--
-- 0007 loops over every table this role owns and enables RLS on it, which
-- is what covers tables added by later migrations — but only on the *next*
-- boot. Migrations run in filename order in one pass, so on the startup
-- that first creates these tables, 0007 has already run and seen nothing.
--
-- For most tables that window is a boot cycle of exposure to PostgREST.
-- For this pair it is a boot cycle in which anyone holding the publishable
-- key — which ships in the browser bundle, by design — could read every
-- user's encrypted platform tokens and the ids of everything they posted.
-- Encrypted is not a reason to be relaxed about handing them out.
--
-- So the lockdown is repeated here, scoped to these two tables. It stays
-- correct if 0007 is ever renumbered, and 0007 remains the safety net for
-- whatever the next migration adds.
-- ---------------------------------------------------------------------
alter table social_connections enable row level security;
alter table social_posts enable row level security;

do $$
declare
    v_from text;
begin
    select string_agg(quote_ident(rolname), ', ')
      into v_from
      from pg_roles
     where rolname in ('anon', 'authenticated');

    -- Not a Supabase database: those roles exist nowhere else, and naming
    -- them unconditionally would fail the migration — which runs at boot,
    -- so it would take the API down for every self-hoster.
    if v_from is null then
        raise notice 'no anon/authenticated roles: nothing to revoke';
    else
        execute format('revoke all on social_connections from %s', v_from);
        execute format('revoke all on social_posts from %s', v_from);
    end if;
end;
$$;
