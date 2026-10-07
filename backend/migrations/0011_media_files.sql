-- A user's own files, kept so they can be used again.
--
-- Until now every video and song a user brought belonged to the one
-- project it was uploaded for: making a second caption, a dub or an edit
-- from the same footage meant uploading it again. This is the shelf they
-- live on instead. A project takes a file from here by linking it into
-- its own directory, so deleting either one leaves the other intact.
--
-- The path is not stored. Files sit at a fixed name derived from the id
-- (see services/media_store.py), the same rule projects follow, so no row
-- can ever point ffmpeg somewhere of its choosing.

create table if not exists media_files (
    id           uuid primary key,
    user_id      uuid references app_users(id) on delete cascade,
    kind         text not null check (kind in ('video', 'audio')),
    -- The name it was uploaded with. Shown, never used as a path.
    name         text not null,
    ext          text not null,
    size_bytes   bigint not null,
    duration_s   real,
    width        integer,
    height       integer,
    created_at   timestamptz not null default now()
);

create index if not exists media_files_user_idx on media_files (user_id, created_at desc);

-- Locked down the way 0008 locks its tables, for the reason it gives:
-- 0007 is the safety net, this table should not depend on it.
alter table media_files enable row level security;

do $$
declare
    v_from text;
begin
    select string_agg(quote_ident(rolname), ', ')
      into v_from
      from pg_roles
     where rolname in ('anon', 'authenticated');
    if v_from is null then
        raise notice 'no anon/authenticated roles: nothing to revoke';
    else
        execute format('revoke all on media_files from %s', v_from);
    end if;
end;
$$;
