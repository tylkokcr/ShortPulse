import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Supabase client, or null when this install has no accounts.
 *
 * Both shapes of the product are served from the same build: the hosted
 * service sets these env vars, a self-hosted install doesn't and never
 * sees a login screen. Everything auth-related keys off `supabase !== null`
 * rather than a separate flag, so the two can't drift apart.
 *
 * The publishable key is public by design — it only lets the browser start
 * a login flow, and grants no data access on its own.
 */
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

export const supabase: SupabaseClient | null =
  url && publishableKey ? createClient(url, publishableKey) : null;

export const authEnabled = supabase !== null;
