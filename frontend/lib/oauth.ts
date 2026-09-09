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
 * Check that Supabase will actually start this flow, before leaving.
 *
 * Supabase does *not* report a disabled provider the way it reports every
 * other auth failure. An expired magic link comes back to our own page
 * with `error` in the fragment, which is what readLinkError() reads. A
 * provider that has not been configured in the dashboard instead answers
 * the authorize request with a bare 400 JSON body:
 *
 *   {"code":400,"error_code":"validation_failed",
 *    "msg":"Unsupported provider: provider is not enabled"}
 *
 * There is no redirect, so nothing of ours ever runs again. Left alone,
 * pressing the main sign-in button strands the visitor on raw JSON with
 * no way back — and this is a reachable state, not a hypothetical one:
 * it is what a deployment looks like between shipping a provider in
 * NEXT_PUBLIC_OAUTH_PROVIDERS and enabling it in the Supabase dashboard.
 *
 * So the URL is fetched before the browser is sent to it. A configured
 * provider answers with a redirect to Google or Facebook, which `fetch`
 * reports as an opaque response it cannot read — that opacity is the
 * success signal here, not a problem.
 *
 * Fails open. If the check itself cannot run — offline, blocked, a
 * timeout — the browser goes anyway: a working sign-in must not be
 * blocked by a guard against a misconfiguration.
 */
async function providerIsEnabled(url: string): Promise<string | null> {
  try {
    const response = await fetch(url, { redirect: "manual" });
    // An opaque redirect (status 0) is the healthy case: it means Supabase
    // is sending the browser on to the provider.
    if (response.status === 0 || response.ok) return null;
    if (response.status >= 400 && response.status < 500) {
      const body = await response.text();
      return body.slice(0, 300);
    }
    return null;
  } catch {
    return null;
  }
}

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
 * Failures *after* the provider has been reached arrive in that same
 * fragment and are read by readLinkError() in LoginScreen. Failures
 * before it are the case providerIsEnabled exists for.
 *
 * `skipBrowserRedirect` is what makes the check possible: supabase-js
 * builds the authorize URL and hands it back instead of navigating, so
 * the URL that gets tested is the exact one the browser will visit rather
 * than a second copy assembled here.
 */
export async function signInWithProvider(
  provider: OAuthProvider,
  redirectTo: string
): Promise<void> {
  if (!supabase) throw new Error("This install has no accounts.");

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: { redirectTo, skipBrowserRedirect: true },
  });
  if (error) throw error;
  if (!data?.url) throw new Error("Couldn't start sign-in. Try again.");

  const problem = await providerIsEnabled(data.url);
  if (problem) throw new Error(problem);

  window.location.assign(data.url);
}
