"use client";

import { useEffect, useState } from "react";
import { Mail, ArrowRight } from "lucide-react";
import clsx from "clsx";
import { supabase } from "@/lib/supabase";
import {
  oauthProviders,
  signInWithProvider,
  PROVIDER_LABELS,
  type OAuthProvider,
} from "@/lib/oauth";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { GoogleIcon, FacebookIcon } from "@/components/auth/ProviderIcons";
import { useSignupCredits } from "@/lib/signupCredits";

/**
 * Supabase's auth errors are written for developers. Rewrite the ones a
 * user can actually act on; pass anything else through rather than
 * inventing a friendlier message for a problem we haven't identified.
 */
function explain(message: string): string {
  const text = message.toLowerCase();
  if (text.includes("rate limit")) {
    return (
      "Too many sign-in emails in a short time. Check your inbox — including spam — " +
      "for a link we already sent, or try again in an hour."
    );
  }
  if (text.includes("invalid") && text.includes("email")) {
    return "That doesn't look like a valid email address.";
  }
  if (text.includes("signups not allowed") || text.includes("signup is disabled")) {
    return "This address isn't allowed to sign up yet.";
  }
  // A provider that is listed in NEXT_PUBLIC_OAUTH_PROVIDERS but was never
  // switched on in the Supabase dashboard. A user can do nothing about it,
  // so point them at the door that does open rather than at the setting.
  if (text.includes("provider is not enabled") || text.includes("unsupported provider")) {
    return "That sign-in method isn't available right now. Use your email address instead.";
  }
  return message;
}

/**
 * What Supabase says when a clicked link doesn't work.
 *
 * These arrive in the URL fragment on the page the link opened, never as a
 * thrown error, so nothing in the app sees them unless it goes looking.
 * Until it did, clicking an expired link signed you out onto the landing
 * page with no explanation — indistinguishable from the link doing
 * nothing at all, which is what a stranger would conclude.
 *
 * OAuth failures land in exactly the same place, for the same reason, so
 * this function covers both — the provider ones were free.
 */
function explainLinkError(code: string, description: string): string {
  if (code === "otp_expired") {
    return (
      "That sign-in link has expired or was already used — they work once, and " +
      "some mail providers open links to scan them. Send yourself a fresh one."
    );
  }
  // Facebook accounts registered with a phone number have no email to
  // hand over, and Supabase needs one to key the account on. The user
  // reads this as "Facebook didn't work" and needs to be told the way in
  // that does, not the reason it didn't.
  if (description.toLowerCase().includes("email")) {
    if (description.toLowerCase().includes("external provider")) {
      return (
        "That account didn't share an email address with us, and we need one to " +
        "identify you. Sign in with your email below instead."
      );
    }
  }
  if (code === "access_denied") {
    // Also what a cancelled provider consent screen reports. Saying the
    // link is invalid to someone who simply pressed "Cancel" would be
    // describing a failure that didn't happen.
    return description.toLowerCase().includes("denied")
      ? "Sign-in was cancelled. Nothing happened — try again whenever you like."
      : "That sign-in link is no longer valid. Send yourself a fresh one.";
  }
  return description || "That sign-in link didn't work. Send yourself a fresh one.";
}

/**
 * Read an auth failure out of the URL the link landed on.
 *
 * The fragment is where Supabase puts a *successful* session too, and
 * supabase-js consumes that itself — so this only ever looks for `error`
 * and leaves everything else alone. The query string is checked as well
 * because the PKCE flow reports there instead.
 */
function readLinkError(): string | null {
  if (typeof window === "undefined") return null;
  for (const raw of [window.location.hash.replace(/^#/, ""), window.location.search.replace(/^\?/, "")]) {
    const params = new URLSearchParams(raw);
    const error = params.get("error") || params.get("error_code");
    if (!error) continue;
    // Clear it, so a refresh doesn't re-accuse a link the user has since
    // replaced, and so the address bar stops showing raw error codes.
    window.history.replaceState(null, "", window.location.pathname);
    return explainLinkError(
      params.get("error_code") || error,
      params.get("error_description")?.replace(/\+/g, " ") ?? ""
    );
  }
  return null;
}

const PROVIDER_ICONS: Record<OAuthProvider, (props: { size?: number }) => React.ReactNode> = {
  google: GoogleIcon,
  facebook: FacebookIcon,
};

/**
 * Sign-in card: identity providers first, email link underneath.
 *
 * The email link is not a legacy path kept out of sentiment. Facebook
 * accounts registered against a phone number hand over no email address,
 * Google accounts are not universal, and every account that existed
 * before this screen did was created by a link — so removing it would
 * lock out real users to tidy up the layout. It sits below a divider
 * because it is the slower of the two and shouldn't be what the eye lands
 * on.
 *
 * With no providers configured this degrades to exactly the card that was
 * here before: heading, email field, button.
 */
export function LoginPanel({ className }: { className?: string }) {
  const signupCredits = useSignupCredits();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  // Which provider is mid-redirect. The browser is on its way out, but on
  // a slow connection that takes long enough for a second click to start
  // a second flow.
  const [redirecting, setRedirecting] = useState<OAuthProvider | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A failed link or a refused provider lands here rather than on a route
  // of its own, so the panel that starts sign-in is also the panel that
  // reports it failing.
  useEffect(() => {
    const failure = readLinkError();
    if (failure) setError(failure);
  }, []);

  async function startProvider(provider: OAuthProvider) {
    setError(null);
    setRedirecting(provider);
    try {
      // Back to where they started. Sending everyone to "/" would drop a
      // visitor who opened /login from a project link onto the studio
      // instead of the thing they were trying to reach.
      await signInWithProvider(provider, window.location.href);
    } catch (err) {
      setError(explain(err instanceof Error ? err.message : String(err)));
      setRedirecting(null);
    }
  }

  async function sendLink(event: React.FormEvent) {
    event.preventDefault();
    if (!supabase) return;

    setStatus("sending");
    setError(null);
    const { error: sendError } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    });

    if (sendError) {
      setError(explain(sendError.message));
      setStatus("idle");
      return;
    }
    setStatus("sent");
  }

  return (
    <Card
      id="sign-in"
      className={clsx(
        "relative flex flex-col gap-4 overflow-hidden bg-surface-raised shadow-2xl shadow-black/40",
        className
      )}
    >
      {status === "sent" ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-sm font-medium text-white">
            <Mail size={16} className="text-accent" />
            Check your inbox
          </div>
          <p className="text-sm text-white/50">
            We sent a sign-in link to <span className="text-white/80">{email}</span>. It opens this
            page already signed in. If it isn&apos;t there in a minute, check spam.
          </p>
          <button
            onClick={() => setStatus("idle")}
            className="self-start text-xs text-white/40 underline underline-offset-2 hover:text-white/70"
          >
            Use a different address
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div>
            <h2 className="text-base font-semibold text-white">
              Start with {signupCredits} free credits
            </h2>
            <p className="mt-1 text-sm text-white/50">
              No card, no subscription. One account, however you sign in.
            </p>
          </div>

          {oauthProviders.length > 0 && (
            <div className="flex flex-col gap-2">
              {oauthProviders.map((provider) => {
                const Icon = PROVIDER_ICONS[provider];
                return (
                  <Button
                    key={provider}
                    type="button"
                    variant="secondary"
                    onClick={() => startProvider(provider)}
                    disabled={redirecting !== null}
                    className="w-full"
                  >
                    <Icon size={17} />
                    {redirecting === provider
                      ? `Opening ${PROVIDER_LABELS[provider]}...`
                      : `Continue with ${PROVIDER_LABELS[provider]}`}
                  </Button>
                );
              })}
            </div>
          )}

          {/* The error sits above the divider because it can come from
              either half — a refused provider or a dead link. */}
          {error && <p className="text-sm text-red-400">{error}</p>}

          {oauthProviders.length > 0 && (
            <div className="flex items-center gap-3" aria-hidden>
              <span className="h-px flex-1 bg-border" />
              <span className="text-xs uppercase tracking-wider text-white/25">or</span>
              <span className="h-px flex-1 bg-border" />
            </div>
          )}

          <form onSubmit={sendLink} className="flex flex-col gap-3">
            <label className="sr-only" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="rounded-lg border border-border bg-black/30 px-3 py-2.5 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
            />
            <Button
              type="submit"
              variant={oauthProviders.length > 0 ? "outline" : "gradient"}
              disabled={status === "sending" || !email.trim() || redirecting !== null}
            >
              {status === "sending" ? "Sending..." : "Email me a sign-in link"}
              {status !== "sending" && <ArrowRight size={16} />}
            </Button>
          </form>

          <p className="text-xs text-white/30">
            Prefer to run it yourself?{" "}
            <a
              href="https://github.com/tylkokcr/ShortPulse"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2 hover:text-white/60"
            >
              Clone the repo
            </a>{" "}
            — MIT licensed, no account needed.
          </p>
        </div>
      )}
    </Card>
  );
}
