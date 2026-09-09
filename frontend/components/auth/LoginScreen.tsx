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
  // The single most likely wrong guess here is not a mistyped password: it
  // is an account that has never had one. Every account made before this
  // screen existed was created by a sign-in link or by Google, and Supabase
  // reports "no password on file" and "wrong password" with the same
  // string. Naming both readings costs one sentence and saves the user
  // from retyping a password they never chose.
  if (text.includes("invalid login credentials")) {
    return (
      "That email and password don't match. If you've only ever signed in with " +
      "Google or a sign-in link, you don't have a password yet — use " +
      "“Forgot your password?” to set one."
    );
  }
  if (text.includes("already registered") || text.includes("user already exists")) {
    return "There's already an account with that address. Sign in instead.";
  }
  if (text.includes("password should be") || text.includes("password is too short")) {
    return "Passwords need to be at least 8 characters.";
  }
  if (text.includes("email not confirmed")) {
    return "Confirm your email address first — check your inbox for the link we sent.";
  }
  if (text.includes("same password")) {
    return "That's the password you already had. Pick a different one.";
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
type Mode = "signin" | "signup";

/** What the panel is waiting on. One at a time, so a second submit while
 *  the first is in flight can't start a competing request. */
type Busy = "password" | "link" | "reset" | null;

/** The three things that end with "go and look in your email". They differ
 *  only in wording, so they share one screen rather than three. */
type Sent = { kind: "link" | "confirm" | "reset"; address: string } | null;

export function LoginPanel({ className }: { className?: string }) {
  const signupCredits = useSignupCredits();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<Busy>(null);
  const [sent, setSent] = useState<Sent>(null);
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

  /**
   * Email and password, in both directions.
   *
   * Signing up does not always produce a session. With "Confirm email" on
   * in the Supabase dashboard, signUp succeeds, returns no session, and the
   * account stays unusable until a link is clicked; with it off, the
   * session arrives here and AuthProvider takes over. Reading
   * `data.session` rather than assuming one is what lets that dashboard
   * setting change without this file being wrong.
   */
  async function submitPassword(event: React.FormEvent) {
    event.preventDefault();
    if (!supabase) return;

    const address = email.trim();
    setBusy("password");
    setError(null);

    if (mode === "signup") {
      const { data, error: signUpError } = await supabase.auth.signUp({
        email: address,
        password,
        options: { emailRedirectTo: window.location.origin },
      });
      if (signUpError) {
        setError(explain(signUpError.message));
        setBusy(null);
        return;
      }
      if (!data.session) setSent({ kind: "confirm", address });
      setBusy(null);
      return;
    }

    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: address,
      password,
    });
    if (signInError) setError(explain(signInError.message));
    setBusy(null);
  }

  /**
   * The passwordless way in, kept as a second door rather than the front
   * one. Every account that existed before this screen was created by one
   * of these, and a Facebook account registered against a phone number
   * still has no password and no email to make one with.
   */
  async function sendLink() {
    if (!supabase) return;
    const address = email.trim();
    if (!address) {
      setError("Type your email address first.");
      return;
    }

    setBusy("link");
    setError(null);
    const { error: sendError } = await supabase.auth.signInWithOtp({
      email: address,
      options: { emailRedirectTo: window.location.origin },
    });

    if (sendError) {
      setError(explain(sendError.message));
      setBusy(null);
      return;
    }
    setSent({ kind: "link", address });
    setBusy(null);
  }

  /**
   * Also the way an older account gets its first password: Supabase treats
   * "reset" and "set for the first time" as the same operation, which is
   * why the invalid-credentials message points here.
   *
   * Supabase deliberately answers the same way whether or not the address
   * exists, so this screen must not claim an email was sent to a real
   * account — only that one was sent if there is one.
   */
  async function sendReset() {
    if (!supabase) return;
    const address = email.trim();
    if (!address) {
      setError("Type your email address first, then ask for a reset link.");
      return;
    }

    setBusy("reset");
    setError(null);
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(address, {
      redirectTo: `${window.location.origin}/reset-password`,
    });

    if (resetError) {
      setError(explain(resetError.message));
      setBusy(null);
      return;
    }
    setSent({ kind: "reset", address });
    setBusy(null);
  }

  return (
    <Card
      id="sign-in"
      className={clsx(
        "relative flex flex-col gap-4 overflow-hidden bg-surface-raised shadow-2xl shadow-black/40",
        className
      )}
    >
      {sent ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-sm font-medium text-white">
            <Mail size={16} className="text-accent" />
            Check your inbox
          </div>
          <p className="text-sm text-white/50">
            {sent.kind === "link" && (
              <>
                We sent a sign-in link to <span className="text-white/80">{sent.address}</span>. It
                opens this page already signed in.
              </>
            )}
            {sent.kind === "confirm" && (
              <>
                We sent a confirmation link to <span className="text-white/80">{sent.address}</span>.
                Click it once and the account is ready — after that your password works here.
              </>
            )}
            {/* Not "we sent you an email": Supabase answers a reset the same
                way whether or not the address has an account, and saying
                otherwise would turn this form into a way to find out who has
                signed up. */}
            {sent.kind === "reset" && (
              <>
                If <span className="text-white/80">{sent.address}</span> has an account, a link to
                set a new password is on its way. It opens a page where you choose one.
              </>
            )}{" "}
            If it isn&apos;t there in a minute, check spam.
          </p>
          <button
            onClick={() => setSent(null)}
            className="self-start text-xs text-white/40 underline underline-offset-2 hover:text-white/70"
          >
            Back to sign in
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div>
            <h2 className="text-base font-semibold text-white">
              {mode === "signup" ? `Start with ${signupCredits} free credits` : "Welcome back"}
            </h2>
            <p className="mt-1 text-sm text-white/50">
              {mode === "signup"
                ? "No card, no subscription. One account, however you sign in."
                : "One account, however you signed up."}
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

          <form onSubmit={submitPassword} className="flex flex-col gap-3">
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
            <label className="sr-only" htmlFor="password">
              Password
            </label>
            {/* minLength only when signing up. Enforcing it on the way in
                would lock out anyone whose existing password predates the
                rule, and the server is the one that decides anyway. */}
            <input
              id="password"
              type="password"
              required
              minLength={mode === "signup" ? 8 : undefined}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "signup" ? "Choose a password — 8 characters or more" : "Password"}
              className="rounded-lg border border-border bg-black/30 px-3 py-2.5 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
            />
            <Button
              type="submit"
              variant={oauthProviders.length > 0 ? "outline" : "gradient"}
              disabled={busy !== null || redirecting !== null || !email.trim() || !password}
            >
              {busy === "password"
                ? mode === "signup"
                  ? "Creating account..."
                  : "Signing in..."
                : mode === "signup"
                  ? "Create account"
                  : "Sign in"}
              {busy !== "password" && <ArrowRight size={16} />}
            </Button>
          </form>

          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs text-white/40">
            <button
              type="button"
              onClick={() => {
                setMode(mode === "signin" ? "signup" : "signin");
                setError(null);
              }}
              className="underline underline-offset-2 hover:text-white/70"
            >
              {mode === "signin" ? "New here? Create an account" : "Already have an account? Sign in"}
            </button>
            {mode === "signin" && (
              <button
                type="button"
                onClick={sendReset}
                disabled={busy !== null}
                className="underline underline-offset-2 hover:text-white/70 disabled:opacity-50"
              >
                {busy === "reset" ? "Sending..." : "Forgot your password?"}
              </button>
            )}
          </div>

          <div className="rule" />

          {/* Below the rule on purpose: it is the slower way in and the one
              a returning user rarely wants, but it is also the only way in
              for an account that has never had a password. */}
          <button
            type="button"
            onClick={sendLink}
            disabled={busy !== null || redirecting !== null}
            className="self-start text-xs text-white/40 underline underline-offset-2 hover:text-white/70 disabled:opacity-50"
          >
            {busy === "link" ? "Sending..." : "Email me a sign-in link instead"}
          </button>

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
