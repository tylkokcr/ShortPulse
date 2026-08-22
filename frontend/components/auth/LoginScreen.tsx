"use client";

import { useEffect, useState } from "react";
import { Mail, ArrowRight } from "lucide-react";
import clsx from "clsx";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
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
 */
function explainLinkError(code: string, description: string): string {
  if (code === "otp_expired") {
    return (
      "That sign-in link has expired or was already used — they work once, and " +
      "some mail providers open links to scan them. Send yourself a fresh one."
    );
  }
  if (code === "access_denied") {
    return "That sign-in link is no longer valid. Send yourself a fresh one.";
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

/**
 * Magic-link sign-in card. No password field on purpose: passwords would
 * mean a reset flow, a strength policy, and somewhere for users to reuse a
 * password they've already leaked elsewhere. A link to their inbox proves
 * the same thing with none of that.
 *
 * Embedded directly in the landing hero (see components/marketing/Landing)
 * rather than living behind its own route — the fastest path from "reading
 * about the product" to "using it" is not making that a separate page.
 */
export function LoginPanel({ className }: { className?: string }) {
  const signupCredits = useSignupCredits();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  // A failed link lands here rather than on a route of its own, so the
  // panel that sends links is also the panel that reports them failing.
  useEffect(() => {
    const failure = readLinkError();
    if (failure) setError(failure);
  }, []);

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
        <form onSubmit={sendLink} className="flex flex-col gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">
              Start with {signupCredits} free credits
            </h2>
            <p className="mt-1 text-sm text-white/50">
              No card. One-time link, no password to leak or reset.
            </p>
          </div>
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
          {error && <p className="text-sm text-red-400">{error}</p>}
          <Button type="submit" variant="gradient" disabled={status === "sending" || !email.trim()}>
            {status === "sending" ? "Sending..." : "Email me a sign-in link"}
            {status !== "sending" && <ArrowRight size={16} />}
          </Button>
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
        </form>
      )}
    </Card>
  );
}
