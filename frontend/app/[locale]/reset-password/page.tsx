"use client";

import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { useRouter } from "@/i18n/navigation";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { GridBackdrop } from "@/components/ui/GridBackdrop";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/components/auth/AuthProvider";
import { supabase } from "@/lib/supabase";

/**
 * Where a password-reset link lands.
 *
 * Supabase does not hand out a "reset token" for us to post somewhere: the
 * link signs the browser in with a short-lived recovery session, and the
 * new password is set with an ordinary updateUser call on that session.
 * So this page has no token handling of its own — if there is a session
 * when it mounts, the link worked, and if there isn't, it didn't.
 *
 * That also means the page is reachable while already signed in normally,
 * which is fine and useful: it is the only way to change a password from
 * inside the app.
 *
 * It doubles as the way an older account gets its *first* password. Every
 * account made before passwords existed was created by a sign-in link or
 * by Google, and Supabase treats "set" and "reset" as the same write.
 */
export default function ResetPasswordPage() {
  const router = useRouter();
  const { loading, session, enabled } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!loading && !enabled) router.replace("/");
  }, [loading, enabled, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!supabase) return;

    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }

    setBusy(true);
    setError(null);
    const { error: updateError } = await supabase.auth.updateUser({ password });
    if (updateError) {
      // Worth its own message: the recovery session is short-lived, and by
      // the time someone has found the email, opened it on another device
      // and typed a password twice, it can be gone. "Session expired" would
      // read as "your password didn't save" without saying what to do.
      const text = updateError.message.toLowerCase();
      setError(
        text.includes("session") || text.includes("expired")
          ? "That reset link has expired. Ask for a fresh one from the sign-in page."
          : updateError.message
      );
      setBusy(false);
      return;
    }
    setDone(true);
    setBusy(false);
  }

  if (loading || !enabled) return null;

  return (
    <div className="relative flex min-h-screen flex-col">
      <GridBackdrop />

      <SiteHeader />

      <main className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="animate-fade-up flex w-full max-w-sm flex-col gap-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight">
              Choose a <span className="text-accent-emphasis">password</span>
            </h1>
            <p className="mt-2 text-sm text-white/50">
              It replaces whatever was there before, and works alongside Google and sign-in links.
            </p>
          </div>

          <Card className="flex flex-col gap-4 bg-surface-raised shadow-2xl shadow-black/40">
            {done ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2 text-sm font-medium text-white">
                  <KeyRound size={16} className="text-accent" />
                  Password saved
                </div>
                <p className="text-sm text-white/50">
                  You&apos;re signed in on this device already. Next time, use it on the sign-in
                  page.
                </p>
                <Button onClick={() => router.replace("/")} className="self-start">
                  Go to the studio
                </Button>
              </div>
            ) : !session ? (
              // No session means the link is spent, was opened in a
              // different browser, or somebody navigated here directly.
              // All three end the same way, so they get one answer.
              <div className="flex flex-col gap-3">
                <p className="text-sm text-white/60">
                  This page needs a working reset link. Ask for a fresh one and open it in this
                  browser.
                </p>
                <Button variant="outline" onClick={() => router.push("/login")} className="self-start">
                  Back to sign in
                </Button>
              </div>
            ) : (
              <form onSubmit={submit} className="flex flex-col gap-3">
                <label className="sr-only" htmlFor="new-password">
                  New password
                </label>
                <input
                  id="new-password"
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="New password — 8 characters or more"
                  className="rounded-lg border border-border bg-black/30 px-3 py-2.5 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
                />
                <label className="sr-only" htmlFor="confirm-password">
                  Repeat password
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="Repeat it"
                  className="rounded-lg border border-border bg-black/30 px-3 py-2.5 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
                />

                {error && <p className="text-sm text-red-400">{error}</p>}

                <Button type="submit" disabled={busy || !password || !confirm}>
                  {busy ? "Saving..." : "Save password"}
                </Button>
              </form>
            )}
          </Card>
        </div>
      </main>
    </div>
  );
}
