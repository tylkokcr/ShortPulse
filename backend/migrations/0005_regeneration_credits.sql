-- Let a credit charge say it was a scene re-roll rather than a render.
--
-- Re-rolling one scene of a finished video is the first thing that takes
-- money after the render is over, and 0001 gave spend_credits no way to
-- say so: it writes `reason = 'render'` unconditionally (0001:152).
--
-- That is not a labelling nicety. refund_project sums *every* row with
-- `reason = 'render'` for a project (0001:177-179), so a re-roll charge
-- filed under that name becomes part of what a project refund pays back.
-- The failure that follows is quiet and expensive: a customer buys a
-- video, re-rolls four scenes, the render is later refunded for an
-- unrelated reason, and the refund hands back the re-rolls too.
--
-- Worse in combination with reconcile_interrupted_renders, which refunds
-- anything left in status `rendering` at startup. Regeneration therefore
-- never touches project status — but the ledger should not depend on that
-- discipline holding forever.

-- The check constraint is unnamed in 0001, so Postgres derived
-- credit_entries_reason_check from the column.
alter table credit_entries drop constraint if exists credit_entries_reason_check;
alter table credit_entries add constraint credit_entries_reason_check
    check (reason in ('purchase', 'grant', 'render', 'refund', 'adjustment', 'regenerate'));

-- Drop before create, not an overload.
--
-- Adding a defaulted sixth parameter to the existing five-argument
-- function makes every current call site ambiguous — Postgres resolves
-- spend_credits($1,$2,$3,$4,$5) against both signatures and raises
-- "function spend_credits(...) is not unique" rather than picking one.
-- The argument types have to be spelled out here because that is how a
-- function is identified for dropping.
drop function if exists spend_credits(uuid, integer, uuid, text, text);

create or replace function spend_credits(
    p_user     uuid,
    p_amount   integer,
    p_project  uuid default null,
    p_key      text default null,
    p_note     text default null,
    -- Defaulted so the shape of every existing caller is unchanged, and
    -- so a caller that has no opinion files an ordinary render charge.
    p_reason   text default 'render'
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
    values (p_user, -p_amount, p_reason, p_project, p_key, p_note);

    return v_balance - p_amount;
end;
$$;

-- refund_project is deliberately left alone. Its `where reason = 'render'`
-- now excludes re-rolls by construction, which is the whole point: a
-- re-roll is a separate purchase of a separate thing, and giving a render
-- back does not un-buy it.
