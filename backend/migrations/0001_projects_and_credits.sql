-- ShortPulse: persistent projects + credit ledger.
--
-- Targets Postgres, so it runs identically on Supabase and on a local
-- container. Supabase provides auth.users; this file references it only if
-- present, so the same schema can be applied to a plain Postgres for tests.

-- gen_random_uuid()
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- app_users
--
-- Mirror of the authenticated user. On Supabase, id equals auth.users.id;
-- locally it stands alone so the ledger can be tested without an auth
-- provider. Keeping our own row means project/ledger foreign keys don't
-- depend on a schema we don't control.
-- ---------------------------------------------------------------------
create table if not exists app_users (
    id          uuid primary key default gen_random_uuid(),
    email       text unique,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- projects
--
-- Replaces the in-memory dict in services/project_store.py, which lost
-- every project (and cancelled every in-flight render) on restart.
-- `config` and `script` stay as JSONB: they mirror Pydantic models that
-- still change shape often, and nothing queries inside them.
-- ---------------------------------------------------------------------
create table if not exists projects (
    id            uuid primary key,
    user_id       uuid references app_users(id) on delete cascade,
    status        text not null default 'draft'
                  check (status in ('draft', 'rendering', 'complete', 'failed')),
    config        jsonb not null,
    script        jsonb,
    output_path   text,
    error         text,
    credits_cost  integer not null default 0,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists projects_user_created_idx
    on projects (user_id, created_at desc);

-- Renders that were in flight when the process died. Nothing will ever
-- move them forward, so a reconciler needs to find and refund them.
create index if not exists projects_rendering_idx
    on projects (status) where status = 'rendering';

-- ---------------------------------------------------------------------
-- credit_entries — append-only ledger
--
-- Balance is never stored, only derived: sum(delta) for a user. A stored
-- balance column would be a second source of truth that can silently drift
-- from the entries; deriving it means the audit trail is the balance.
--
-- delta > 0: purchase, promotional grant, or refund
-- delta < 0: spend
--
-- Rows are never updated or deleted. A mistake is corrected by appending a
-- compensating entry, so history stays intact.
-- ---------------------------------------------------------------------
create table if not exists credit_entries (
    id               bigserial primary key,
    user_id          uuid not null references app_users(id) on delete cascade,
    delta            integer not null check (delta <> 0),
    reason           text not null
                     check (reason in ('purchase', 'grant', 'render', 'refund', 'adjustment')),
    project_id       uuid references projects(id) on delete set null,
    -- Caller-supplied dedupe key. Retrying a charge with the same key is a
    -- no-op rather than a second debit, which is what makes the HTTP layer
    -- and the job queue safe to retry.
    idempotency_key  text,
    note             text,
    created_at       timestamptz not null default now()
);

create unique index if not exists credit_entries_idem_idx
    on credit_entries (user_id, idempotency_key)
    where idempotency_key is not null;

create index if not exists credit_entries_user_idx
    on credit_entries (user_id, created_at desc);

-- At most one refund per project, so a retried failure handler or a
-- reconciler racing the request path cannot refund the same render twice.
create unique index if not exists credit_entries_one_refund_per_project_idx
    on credit_entries (project_id)
    where reason = 'refund' and project_id is not null;

-- ---------------------------------------------------------------------
-- Balance + atomic spend
--
-- The dangerous shape is read-balance / check / write, which lets two
-- concurrent requests both observe a sufficient balance and both spend it.
-- spend_credits takes a per-user transaction-scoped advisory lock so
-- concurrent debits for the same user serialize, while different users
-- stay fully parallel. The lock is released automatically at commit.
-- ---------------------------------------------------------------------
create or replace function credit_balance(p_user uuid)
returns integer
language sql
stable
as $$
    select coalesce(sum(delta), 0)::integer
    from credit_entries
    where user_id = p_user;
$$;

create or replace function spend_credits(
    p_user     uuid,
    p_amount   integer,
    p_project  uuid default null,
    p_key      text default null,
    p_note     text default null
)
returns integer          -- balance after the spend
language plpgsql
as $$
declare
    v_existing integer;
    v_balance  integer;
begin
    if p_amount <= 0 then
        raise exception 'spend amount must be positive, got %', p_amount
            using errcode = 'check_violation';
    end if;

    perform pg_advisory_xact_lock(hashtextextended(p_user::text, 0));

    -- Replaying the same key must not charge twice.
    if p_key is not null then
        select id into v_existing
        from credit_entries
        where user_id = p_user and idempotency_key = p_key;

        if found then
            return credit_balance(p_user);
        end if;
    end if;

    v_balance := credit_balance(p_user);
    if v_balance < p_amount then
        raise exception 'insufficient credits: balance % < cost %', v_balance, p_amount
            using errcode = 'insufficient_privilege';
    end if;

    insert into credit_entries (user_id, delta, reason, project_id, idempotency_key, note)
    values (p_user, -p_amount, 'render', p_project, p_key, p_note);

    return v_balance - p_amount;
end;
$$;

-- Give back exactly what a project was charged, at most once. Safe to call
-- from both the failure path and a reconciler without coordinating them.
create or replace function refund_project(p_project uuid, p_note text default null)
returns integer          -- credits refunded (0 if nothing to refund)
language plpgsql
as $$
declare
    v_user    uuid;
    v_charged integer;
begin
    select user_id into v_user from projects where id = p_project;
    if v_user is null then
        return 0;
    end if;

    perform pg_advisory_xact_lock(hashtextextended(v_user::text, 0));

    -- Sum of debits for this project; positive number.
    select coalesce(-sum(delta), 0) into v_charged
    from credit_entries
    where project_id = p_project and reason = 'render';

    if v_charged <= 0 then
        return 0;
    end if;

    -- The partial unique index makes a second refund a no-op rather than
    -- an error, so concurrent callers can't both pay it out.
    insert into credit_entries (user_id, delta, reason, project_id, note)
    values (v_user, v_charged, 'refund', p_project, p_note)
    on conflict do nothing;

    if not found then
        return 0;
    end if;
    return v_charged;
end;
$$;
