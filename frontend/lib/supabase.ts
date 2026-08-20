import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Supabase client, or null when this install has no accounts.
 *
 * Both shapes of the product are served from the same build: the hosted
 * service sets these env vars, a self-hosted install doesn't and never
 * sees a login screen. Everything auth-related keys off `supabase !== null`
 * rather than a separate flag, so the two can't drift apart.
 *
 * The publishable key is public by design: it ships in this bundle, and
 * anyone can read it out of the page. What keeps that safe is not the key
 * but the database — Supabase serves every `public` table over PostgREST
 * to whoever holds it, and for a while it did exactly that here. See
 * backend/migrations/0007_lock_down_postgrest.sql, which is what makes the
 * sentence "grants no data access" true rather than merely intended.
 *
 * So this client is for auth and nothing else. Reaching for .from() or
 * .rpc() here would be reaching for tables that now correctly refuse; app
 * data goes through the API in lib/api.ts, which carries the bearer token.
 */
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

export const supabase: SupabaseClient | null =
  url && publishableKey ? createClient(url, publishableKey) : null;

export const authEnabled = supabase !== null;
