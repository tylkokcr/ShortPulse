"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, Coins, Loader2, TriangleAlert } from "lucide-react";
import clsx from "clsx";
import { getCredits, startCheckout } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { CreditPack } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { AccountBar } from "@/components/auth/AccountBar";
import { RequireAuth } from "@/components/auth/RequireAuth";

/**
 * Where a signed-in user tops up.
 *
 * The landing page's pricing section sells to visitors and sends them to
 * sign in; this is the same packs for someone who already has an account,
 * and the only place in the app that can actually start a purchase.
 *
 * The balance is re-fetched on arrival rather than read from the store,
 * because the most common way to land here is coming back from Stripe —
 * and the credits were granted by a webhook the browser never saw.
 */
export default function CreditsPage() {
  return (
    <RequireAuth>
      <Credits />
    </RequireAuth>
  );
}

function Credits() {
  const { credits, setCredits } = useShortPulseStore();
  const params = useSearchParams();
  const justPurchased = params.get("purchase") === "ok";

  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCredits().then(setCredits).catch(() => {});
  }, [setCredits]);

  // Stripe redirects the moment the payment clears, which can be before
  // the webhook has been delivered and the grant written. Rather than
  // showing a stale balance and letting the user think the purchase
  // failed, re-check for a short while after coming back.
  useEffect(() => {
    if (!justPurchased) return;
    const started = credits?.balance ?? 0;
    let tries = 0;
    const timer = window.setInterval(async () => {
      tries += 1;
      const fresh = await getCredits().catch(() => null);
      if (fresh) setCredits(fresh);
      if ((fresh && fresh.balance > started) || tries >= 10) window.clearInterval(timer);
    }, 2000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [justPurchased]);

  async function buy(pack: CreditPack) {
    setPending(pack.id);
    setError(null);
    try {
      const { url } = await startCheckout(pack.id);
      window.location.href = url;
    } catch (err) {
      setError(
        err instanceof Error && err.message.includes("503")
          ? "This install isn't set up to sell credits."
          : err instanceof Error
            ? err.message
            : "Could not start checkout"
      );
      setPending(null);
    }
  }

  const packs = credits?.packs ?? [];

  return (
    <div className="relative min-h-screen">
      <SiteHeader right={<AccountBar />} showLibrary />

      <main className="mx-auto max-w-4xl px-6 pb-24 pt-10">
        <div className="animate-fade-up">
          <span className="label">Credits</span>
          <h1 className="mt-1.5 text-3xl font-semibold tracking-tight">
            {credits?.balance ?? 0} credits
          </h1>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/50">
            One-off packs. Nothing renews, nothing expires, and unused credits stay yours.
          </p>
        </div>

        {justPurchased && (
          <p className="animate-fade-up mt-6 flex items-center gap-2 rounded-md border border-live/40 bg-live/10 px-4 py-3 text-sm text-live">
            <Check size={15} />
            Payment received. Your balance updates as soon as the confirmation reaches us.
          </p>
        )}

        {error && (
          <p className="mt-6 flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            <TriangleAlert size={14} className="mt-0.5 shrink-0" />
            {error}
          </p>
        )}

        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {packs.map((pack) => (
            <Card
              key={pack.id}
              className={clsx(
                "flex flex-col gap-4",
                pack.popular && "border-accent/40 bg-accent/[0.04]"
              )}
            >
              <div className="flex items-start justify-between">
                <span className="font-mono text-3xl font-semibold">
                  ${(pack.price_cents / 100).toFixed(0)}
                </span>
                {pack.popular && <Badge tone="accent">Most picked</Badge>}
              </div>

              <p className="flex items-center gap-1.5 text-sm text-white/70">
                <Coins size={14} className="text-accent" />
                {pack.credits} credits
              </p>
              <p className="text-xs leading-relaxed text-white/40">
                {/* Quoted from the same table the backend charges from. */}
                {pack.credits} stock-footage shorts, or {Math.floor(pack.credits / 3)} with
                AI-generated stills.
              </p>

              <Button
                onClick={() => buy(pack)}
                disabled={pending !== null}
                variant={pack.popular ? "gradient" : "secondary"}
                className="mt-auto w-full"
              >
                {pending === pack.id ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    Opening checkout
                  </>
                ) : (
                  `Buy ${pack.credits}`
                )}
              </Button>
            </Card>
          ))}
        </div>

        <p className="mt-8 text-xs leading-relaxed text-white/30">
          Payment is handled by Stripe — this app never sees your card details. Self-hosting
          costs nothing and needs no account at all.
        </p>
      </main>
    </div>
  );
}
