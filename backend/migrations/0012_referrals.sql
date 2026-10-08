-- Inviting a friend.
--
-- Every account gets one code; a friend who signs up through a link
-- carrying it is recorded here against the account that invited them.
-- The inviter is paid when the friend's first video finishes, not when
-- they sign up: a signup is a Google account anyone can make five of in
-- an afternoon, a finished video is someone actually using the product.

create table if not exists referral_codes (
    user_id     uuid primary key references app_users(id) on delete cascade,
    code        text not null unique,
    created_at  timestamptz not null default now()
);

create table if not exists referrals (
    -- One inviter per account, ever: the first link that brought them.
    referred_id  uuid primary key references app_users(id) on delete cascade,
    referrer_id  uuid not null references app_users(id) on delete cascade,
    created_at   timestamptz not null default now(),
    -- When the friend's first video finished. `rewarded` is false if the
    -- inviter had already been paid for as many friends as are paid for.
    settled_at   timestamptz,
    rewarded     boolean not null default false,
    check (referred_id <> referrer_id)
);

create index if not exists referrals_referrer_idx on referrals (referrer_id);

-- Locked down the way 0011 locks media_files, for the reason 0008 gives.
alter table referral_codes enable row level security;
alter table referrals enable row level security;

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
        execute format('revoke all on referral_codes from %s', v_from);
        execute format('revoke all on referrals from %s', v_from);
    end if;
end;
$$;
