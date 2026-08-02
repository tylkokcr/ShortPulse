"use client";

import { useState } from "react";
import { Mail } from "lucide-react";
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
 * Magic-link sign-in.
 *
 * No password field on purpose: passwords would mean a reset flow, a
 * strength policy, and somewhere for users to reuse a password they've
 * already leaked elsewhere. A link to their inbox proves the same thing
 * with none of that.
 */
export function LoginScreen() {
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
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-6">
      <div>
        <h1 className="text-2xl font-semibold">ShortPulse</h1>
        <p className="mt-1 text-sm text-white/50">
          Turn a topic into a ready-to-post vertical video.
        </p>
      </div>

      <Card className="flex flex-col gap-4">
        {status === "sent" ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm text-white/80">
              <Mail size={16} />
              Check your inbox
            </div>
            <p className="text-sm text-white/50">
              We sent a sign-in link to <span className="text-white/70">{email}</span>. It opens
              this page already signed in. If it isn&apos;t there in a minute, check spam.
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
            <label className="text-sm font-medium text-white/70" htmlFor="email">
              Sign in with your email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="rounded-lg border border-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button type="submit" disabled={status === "sending" || !email.trim()}>
              {status === "sending" ? "Sending..." : "Email me a sign-in link"}
            </Button>
            <p className="text-xs text-white/30">
              No password to remember, and nothing to reset.
            </p>
          </form>
        )}
      </Card>
    </main>
  );
}
