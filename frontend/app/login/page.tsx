"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { LoginPanel } from "@/components/auth/LoginScreen";
import { useAuth } from "@/components/auth/AuthProvider";

/**
 * The sign-in screen.
 *
 * It exists as a route of its own for a reason the embedded version
 * couldn't satisfy: with identity providers in the mix, the browser
 * leaves this app entirely and comes back, and it has to come back
 * *somewhere*. Landing on the marketing page meant a failed or cancelled
 * sign-in dropped the visitor at the top of a sales pitch with an error
 * message halfway down it. Here, the page they return to is the page they
 * left, and the error appears on the form that produced it.
 *
 * The landing page still carries the pitch and now links here, so the
 * short path from "reading about this" to "using it" is one click rather
 * than none — which the provider buttons more than pay back, since that
 * click replaces opening an inbox.
 */
export default function LoginPage() {
  const router = useRouter();
  const { loading, session, enabled } = useAuth();

  useEffect(() => {
    // Already signed in — including the moment right after a provider
    // hands the session back in the URL fragment, which is what makes
    // this the OAuth landing spot as well as the form.
    if (session) {
      router.replace("/");
      return;
    }
    // A self-hosted install has no accounts at all. There is nothing to
    // show here and no way to satisfy a login, so don't pretend there is.
    if (!loading && !enabled) router.replace("/");
  }, [session, loading, enabled, router]);

  // Blank while the session resolves, and blank on the way out. Same
  // reasoning as RequireAuth: the lookup takes milliseconds and a flash
  // of "sign in" at someone who is already signed in looks broken.
  if (loading || session || !enabled) return null;

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />

      <main className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="animate-fade-up flex w-full max-w-sm flex-col gap-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight">
              Sign in to <span className="text-accent-emphasis">ShortPulse</span>
            </h1>
            <p className="mt-2 text-sm text-white/50">
              A password, Google, or a link to your inbox — all three reach the same account.
            </p>
          </div>

          <LoginPanel />

          <p className="text-center text-xs text-white/30">
            By continuing you agree to our{" "}
            <Link href="/terms" className="underline underline-offset-2 hover:text-white/60">
              terms
            </Link>{" "}
            and{" "}
            <Link href="/privacy" className="underline underline-offset-2 hover:text-white/60">
              privacy policy
            </Link>
            .
          </p>
        </div>
      </main>
    </div>
  );
}
