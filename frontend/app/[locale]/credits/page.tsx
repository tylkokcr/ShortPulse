"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, Coins, Loader2, TriangleAlert } from "lucide-react";
import clsx from "clsx";
import { Link } from "@/i18n/navigation";
import { getCredits, getPublicPricing, startCheckout } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { CreditPack } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { formatPrice } from "@/lib/money";
import { Badge } from "@/components/ui/Badge";
import { AppShell } from "@/components/layout/AppShell";
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
      {/* `useSearchParams` below opts the page out of static rendering
          unless it sits under a Suspense boundary, and Next fails the
          build rather than warning.

          It only surfaced with Supabase unconfigured: with auth on,
          RequireAuth renders nothing while the session resolves, so
          prerendering never reached the hook. With auth off — the
          self-hosted shape, and what the container image builds by
          default — it renders straight through and the build dies. */}
      <Suspense fallback={null}>
        <Credits />
      </Suspense>
    </RequireAuth>
  );
}

function Credits() {
  const { credits, setCredits } = useShortPulseStore();
  const params = useSearchParams();
  const justPurchased = params.get("purchase") === "ok";

  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // EU distance selling gives a consumer 14 days to withdraw from an
  // online purchase. Digital content delivered immediately is exempt only
  // if the buyer expressly asked for it to start now and acknowledged
  // losing that right — otherwise credits can be spent on renders and
  // refunded afterwards. So this is a gate on the button, not a footnote.
  const [acknowledged, setAcknowledged] = useState(false);
  // Which modes this deployment can actually render, so the "how many
  // videos does this buy" line doesn't quote one it can't.
  const [generatedStills, setGeneratedStills] = useState(true);
  // Whether this deployment can charge at all. `CreditSummary.enabled` does
  // not answer that — it is true as soon as there is a ledger and a signed-in
  // user, with or without Stripe — so a deployment running on accounts alone
  // showed three priced packs whose buttons could only ever return 503.
  const [sold, setSold] = useState(true);

  useEffect(() => {
    getCredits().then(setCredits).catch(() => {});
    getPublicPricing()
      .then((p) => {
        setGeneratedStills(p.modes.includes("fast_hybrid"));
        setSold(Boolean(p.sold));
      })
      .catch(() => {});
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
    if (!acknowledged) return;
    setPending(pack.id);
    setError(null);
    try {
      const { url } = await startCheckout(pack.id);
      // The rule is about mutating module-scope state. Assigning
      // location.href is a browser navigation, and leaving this page for
      // the provider is the whole point of the function.
      // eslint-disable-next-line react-hooks/immutability
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
    <AppShell section="credits">
        <div className="animate-fade-up">
          <h1 className="text-3xl font-semibold tracking-tight">
            {credits?.balance ?? 0} credits
          </h1>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/50">
            {sold ? (
              <>
                One-off packs. Nothing renews, nothing expires, and unused credits stay yours.
                {credits?.tax_included && " Prices include VAT at your local rate."}
              </>
            ) : (
              // Same sentence the checkout endpoint answers with, said before
              // the click rather than after it.
              <>
                This install isn&apos;t set up to sell credits. What you have doesn&apos;t
                expire, and renders draw from it as usual.
              </>
            )}
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

        {/* Both the withdrawal-rights gate and the packs it gates are about
            making a purchase, so neither belongs on a deployment that cannot
            take one. */}
        {sold && (
          <>
          <label className="mt-8 flex cursor-pointer items-start gap-3 rounded-md border border-border bg-surface p-4 text-xs leading-relaxed text-white/60">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 accent-accent"
            />
            <span>
              I want my credits available immediately, and I understand that by starting to use
              them I give up the 14-day right to withdraw from this purchase. Unused credits can
              still be refunded within 14 days — see the{" "}
              <Link href="/terms" className="underline underline-offset-2 hover:text-white">
                terms
              </Link>
              .
            </span>
          </label>

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
                    {formatPrice(pack.price_cents, credits?.currency)}
                  </span>
                  {pack.popular && <Badge tone="accent">Most picked</Badge>}
                </div>

                <p className="flex items-center gap-1.5 text-sm text-white/70">
                  <Coins size={14} className="text-accent" />
                  {pack.credits} credits
                </p>
                <p className="text-xs leading-relaxed text-white/40">
                  {/* Quoted from the same table the backend charges from, and
                      only for the modes this install can run — the shipped
                      container has no diffusion stack, and offering the
                      generated-stills number there quotes a price for
                      something the API refuses to sell. */}
                  {pack.credits} stock-footage shorts
                  {generatedStills && `, or ${Math.floor(pack.credits / 3)} with AI-generated stills`}
                  .
                </p>

                <Button
                  onClick={() => buy(pack)}
                  disabled={pending !== null || !acknowledged}
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
          </>
        )}

        <p className="mt-4 text-xs leading-relaxed text-white/30">
          {sold && "Payment is handled by Stripe — this app never sees your card details. "}
          Self-hosting costs nothing and needs no account at all.
        </p>
    </AppShell>
  );
}
