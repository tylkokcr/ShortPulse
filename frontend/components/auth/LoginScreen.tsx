"use client";

import { useState } from "react";
import { Mail, ArrowRight } from "lucide-react";
import clsx from "clsx";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

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
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

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
      <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-accent-gradient opacity-20 blur-3xl" />

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
            <h2 className="text-base font-semibold text-white">Start with 15 free credits</h2>
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
