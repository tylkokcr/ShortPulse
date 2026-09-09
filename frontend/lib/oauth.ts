import { supabase } from "./supabase";

/**
 * Which identity providers this deployment can actually offer.
 *
 * A provider is only usable once it has been switched on in the Supabase
 * dashboard with a client id and secret; clicking a button for one that
 * hasn't been is a 400 and an error message naming a setting the user has
 * never heard of. So the buttons are driven by configuration rather than
 * hardcoded, and the list is deliberately empty by default.
 *
 * Empty is the correct default twice over. A self-hosted install has no
 * Supabase at all (see lib/supabase.ts) and shows no login screen. And the
 * hosted deployment enables providers one at a time as their paperwork
 * clears — Google needs only a consent screen, while Facebook is gated on
 * Meta's business verification, which is weeks of a different kind of
 * work. Listing them here is how the two get decoupled.
 *
 *   NEXT_PUBLIC_OAUTH_PROVIDERS=google
 *   NEXT_PUBLIC_OAUTH_PROVIDERS=google,facebook
 */
export type OAuthProvider = "google" | "facebook";

const SUPPORTED: readonly OAuthProvider[] = ["google", "facebook"];

function parseProviders(raw: string | undefined): OAuthProvider[] {
  if (!raw) return [];
  const named = raw
    .split(",")
    .map((name) => name.trim().toLowerCase())
    .filter(Boolean);
  // Unknown names are dropped rather than passed through to Supabase,
  // which would fail at click time on the one screen a stranger sees
  // first. A typo in an env var should cost a missing button, not a
  // broken one.
  return SUPPORTED.filter((provider) => named.includes(provider));
}

export const oauthProviders: OAuthProvider[] = parseProviders(
  process.env.NEXT_PUBLIC_OAUTH_PROVIDERS
);

export const oauthEnabled = oauthProviders.length > 0;

export const PROVIDER_LABELS: Record<OAuthProvider, string> = {
  google: "Google",
  facebook: "Facebook",
};

/**
 * Hand the browser over to the provider.
 *
 * This client runs the implicit flow (supabase-js's default), so the
 * session comes back in the URL fragment of whatever page `redirectTo`
 * names and supabase-js consumes it there itself — which is why there is
 * no callback route in this app. Any page works as a landing spot,
 * because AuthProvider mounts globally and `detectSessionInUrl` does the
 * rest.
 *
 * Failures arrive the same way, in the fragment, and are read by
 * readLinkError() in LoginScreen — the same function that already had to
 * exist for expired magic links.
 *
 * On success this never returns anything useful: the browser is already
 * navigating away. Only a refusal to start the flow at all — a provider
 * that isn't enabled, most likely — comes back as a thrown error.
 */
export async function signInWithProvider(
  provider: OAuthProvider,
  redirectTo: string
): Promise<void> {
  if (!supabase) throw new Error("This install has no accounts.");

  const { error } = await supabase.auth.signInWithOAuth({
    provider,
    options: { redirectTo },
  });
  if (error) throw error;
}
