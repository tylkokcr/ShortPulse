-- What is trending, per region: the raw data collected from the platforms'
-- own APIs, and the analysis written from it.
--
-- Snapshots are pruned after 30 days: YouTube's API terms ask that data
-- from it be refreshed or deleted within that time, and a trend older
-- than a month is history, not a trend.

create table if not exists trend_snapshots (
    id          bigserial primary key,
    region      text not null,
    fetched_at  timestamptz not null default now(),
    data        jsonb not null
);
create index if not exists trend_snapshots_region_idx on trend_snapshots (region, fetched_at desc);

create table if not exists trend_reports (
    region        text not null,
    lang          text not null,
    generated_at  timestamptz not null default now(),
    snapshot_id   bigint references trend_snapshots(id) on delete cascade,
    report        jsonb not null,
    primary key (region, lang)
);

alter table trend_snapshots enable row level security;
alter table trend_reports enable row level security;

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
        execute format('revoke all on trend_snapshots from %s', v_from);
        execute format('revoke all on trend_reports from %s', v_from);
        execute format('revoke all on sequence trend_snapshots_id_seq from %s', v_from);
    end if;
end;
$$;
