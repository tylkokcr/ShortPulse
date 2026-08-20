-- Close the door this database never knew it had open.
--
-- Supabase serves every table in the `public` schema over PostgREST, at
-- https://<project>.supabase.co/rest/v1/<table>, to anyone holding the
-- publishable key. That key ships in the browser bundle — it is meant to,
-- it is how the login form reaches the auth server — so "anyone" means
-- anyone who views source on the landing page.
--
-- Two Postgres defaults combine into the hole. Supabase's ALTER DEFAULT
-- PRIVILEGES grants new tables in `public` to `anon` and `authenticated`,
-- and Postgres grants EXECUTE on new functions to PUBLIC. Neither is
-- visible from the application: this backend connects as the owning role
-- and has never once been refused, so nothing in the app, the tests or
-- the logs could ever have shown it. It took an email from the vendor.
--
-- The fix is the shape of the architecture rather than a compromise with
-- it. Nothing in the browser reads these tables — frontend/lib/supabase.ts
-- creates a client for auth and never calls .from() or .rpc() — so the
-- correct number of rows for `anon` to see is zero, and the correct
-- number of policies to write is none. RLS with no policy denies
-- everything, which is exactly the intent.
--
-- Why this does not lock out the application: RLS is not enforced against
-- a table's owner unless FORCE ROW LEVEL SECURITY is set, and it is
-- deliberately not set below. The backend owns these tables (it created
-- them, through this same connection) and keeps full access. On Supabase
-- the `postgres` role additionally carries BYPASSRLS, so the guarantee
-- holds twice over.
--
-- Two things keep this from breaking installs that are not Supabase:
--
--   * Everything is scoped to objects *this role owns*. `create extension
--     pgcrypto` in 0001 can land gen_random_uuid() in this same schema and
--     app_users.id defaults to it, so a schema-wide REVOKE would break
--     account creation — an outage that surfaces as "signup is broken" for
--     a stranger, days later, with nothing in the diff pointing at it.
--   * `anon` and `authenticated` are Supabase's roles and exist nowhere
--     else. Naming them unconditionally raises "role does not exist",
--     which in a migration that runs at boot means the API does not start
--     — for every self-hoster, on a plain Postgres, to fix a hole that
--     only ever existed on Supabase. So the list is built from the roles
--     the server actually has.

-- ---------------------------------------------------------------------
-- Tables
--
-- A loop rather than four statements, because migrations here re-run on
-- every startup (see db.apply_migrations): a table added by a later
-- migration is locked down the next time the API boots, instead of
-- waiting for someone to notice a second vendor email. Tables that carry
-- their own policies are covered too — enabling RLS is what makes a
-- policy mean anything.
--
-- Harmless where there is no PostgREST in front: the owner is exempt, so
-- on a self-hosted Postgres this is a flag nothing ever reads.
-- ---------------------------------------------------------------------
do $$
declare
    r record;
begin
    for r in
        select c.oid::regclass as t
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind = 'r'
          and not c.relrowsecurity
          and pg_get_userbyid(c.relowner) = current_user
    loop
        execute format('alter table %s enable row level security', r.t);
        raise notice 'RLS enabled on %', r.t;
    end loop;
end;
$$;

-- ---------------------------------------------------------------------
-- Grants
--
-- Belt and braces on the tables: RLS alone is enough, but a grant is what
-- puts a table in PostgREST's schema at all, so revoking means a future
-- table whose RLS someone switches off by hand is still not served.
--
-- Not belt and braces on the functions — that is the louder half of the
-- same hole, and the one the vendor's linter did not rate critical.
-- PostgREST exposes a `public` function as an RPC endpoint when the caller
-- may execute it, and Postgres grants EXECUTE to PUBLIC by default, so
-- /rest/v1/rpc/refund_project was in principle an unauthenticated write
-- appending positive rows to the credit ledger. Its `on conflict do
-- nothing` bounds that to one refund per project, which is a bound, not a
-- defence.
--
-- Functions are found by owner rather than by signature on purpose. 0005
-- already had to drop and recreate spend_credits to add a parameter, and a
-- hardcoded argument list here would turn the next such change into a
-- failed migration at startup — which is to say, into an API that does not
-- boot. Pinning search_path in the same pass answers the "Function Search
-- Path Mutable" warnings; none of these is SECURITY DEFINER, so that is
-- hardening rather than a hole, and pg_temp goes last because a temporary
-- table shadowing a real one is the mechanism being defended against.
-- ---------------------------------------------------------------------
do $$
declare
    r      record;
    v_from text;
begin
    select string_agg(quote_ident(rolname), ', ')
      into v_from
      from pg_roles
     where rolname in ('anon', 'authenticated');

    if v_from is null then
        raise notice 'no anon/authenticated roles: not a Supabase database, nothing exposed';
    else
        for r in
            select c.oid::regclass as t
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public'
              and c.relkind = 'r'
              and pg_get_userbyid(c.relowner) = current_user
        loop
            execute format('revoke all on %s from %s', r.t, v_from);
        end loop;
    end if;

    -- PUBLIC is not a role and always exists, so the function half runs
    -- everywhere. It is also the grant that actually opened the RPC.
    v_from := concat_ws(', ', 'public', v_from);

    for r in
        select p.oid::regprocedure as f
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and pg_get_userbyid(p.proowner) = current_user
    loop
        execute format('revoke all on function %s from %s', r.f, v_from);
        execute format('alter function %s set search_path = public, pg_temp', r.f);
    end loop;
end;
$$;
