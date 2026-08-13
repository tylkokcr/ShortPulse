"use client";

import { useEffect, useState } from "react";
import { Check, Sparkles, Github } from "lucide-react";
import clsx from "clsx";
import { getCredits } from "@/lib/api";
import type { CreditPack } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { formatPrice } from "@/lib/money";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

const REPO_URL = "https://github.com/tylkokcr/ShortPulse";

/**
 * Mirrors backend `credits.CREDIT_PACKS`. The live values are fetched
 * below — these exist so a marketing page still sells when the API is
 * unreachable, which is exactly when you least want a blank pricing table.
 */
const FALLBACK_PACKS: CreditPack[] = [
  { id: "starter", credits: 100, price_cents: 900, popular: false },
  { id: "creator", credits: 400, price_cents: 2900, popular: true },
  { id: "studio", credits: 1200, price_cents: 7900, popular: false },
];

const PACK_LABELS: Record<string, { name: string; blurb: string }> = {
  starter: { name: "Starter", blurb: "Testing the water on a posting habit." },
  creator: { name: "Creator", blurb: "A daily short with room to redo the ones that miss." },
  studio: { name: "Studio", blurb: "Multiple accounts, or a client workload." },
};

/** Cheapest real render (stock_media + short) costs 1 credit; the default
 *  fast_hybrid short costs 3. Quoting both keeps "how many videos" honest
 *  instead of advertising only the flattering number. */
function videosFor(credits: number) {
  return { basic: credits, standard: Math.floor(credits / 3) };
}

export function Pricing() {
  const [packs, setPacks] = useState<CreditPack[]>(FALLBACK_PACKS);
  // Currency and whether VAT is already in the price are deployment
  // settings, so they come from the server alongside the packs.
  const [currency, setCurrency] = useState("usd");
  const [taxIncluded, setTaxIncluded] = useState(false);

  useEffect(() => {
    getCredits()
      .then((summary) => {
        if (summary.packs?.length) setPacks(summary.packs);
        if (summary.currency) setCurrency(summary.currency);
        setTaxIncluded(Boolean(summary.tax_included));
      })
      .catch(() => {
        /* Keep the fallback — see FALLBACK_PACKS. */
      });
  }, []);

  return (
    <section id="pricing" className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">Pricing</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Pay for videos, not for a month you didn&apos;t use
        </h2>
        <p className="max-w-xl text-sm text-white/50">
          Credits are one-off and never expire. No plan renews, nothing charges you again unless you
          buy again — and the whole thing is still MIT if you&apos;d rather run it yourself.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <Card className="flex flex-col gap-4 bg-surface-raised">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">Free</h3>
            <p className="text-xs text-white/40">Every new account, no card.</p>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-semibold tracking-tight">$0</span>
          </div>
          <ul className="flex flex-col gap-2 text-xs text-white/50">
            <Feature>15 credits on sign-up</Feature>
            <Feature>5 standard videos, or 15 stock-footage ones</Feature>
            <Feature>Every language and visual engine</Feature>
            <Feature>No watermark</Feature>
          </ul>
          <a href="#sign-in" className="mt-auto pt-2">
            <Button variant="secondary" className="w-full">
              Start free
            </Button>
          </a>
        </Card>

        {packs.map((pack) => {
          const label = PACK_LABELS[pack.id] ?? { name: pack.id, blurb: "" };
          const { basic, standard } = videosFor(pack.credits);
          return (
            <Card
              key={pack.id}
              className={clsx(
                "relative flex flex-col gap-4",
                pack.popular
                  ? "border-accent/50 bg-surface-raised shadow-lg shadow-accent/10"
                  : "bg-surface-raised"
              )}
            >
              {pack.popular && (
                <Badge tone="accent" className="absolute -top-2.5 right-4">
                  <Sparkles size={11} />
                  Most picked
                </Badge>
              )}

              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-semibold">{label.name}</h3>
                <p className="text-xs text-white/40">{label.blurb}</p>
              </div>

              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-semibold tracking-tight">
                  {formatPrice(pack.price_cents, currency)}
                  {taxIncluded && (
                    <span className="ml-1.5 align-middle text-[10px] font-normal text-white/30">
                      incl. VAT
                    </span>
                  )}
                </span>
                <span className="text-xs text-white/40">one-off</span>
              </div>

              <ul className="flex flex-col gap-2 text-xs text-white/50">
                <Feature>
                  <span className="text-white/80">{pack.credits} credits</span>
                </Feature>
                <Feature>~{standard} standard videos</Feature>
                <Feature>~{basic} with stock footage</Feature>
                <Feature>Never expire</Feature>
              </ul>

              <a href="#sign-in" className="mt-auto pt-2">
                <Button variant={pack.popular ? "gradient" : "secondary"} className="w-full">
                  Get {pack.credits} credits
                </Button>
              </a>
            </Card>
          );
        })}
      </div>

      <Card className="mt-4 flex flex-col gap-4 border-dashed sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Github size={15} className="text-white/50" />
            Or pay nothing at all
          </h3>
          <p className="text-xs text-white/50">
            Self-host it and the price is zero, forever — credits only exist because the hosted
            instance runs renders on hardware someone has to pay for.
          </p>
        </div>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="shrink-0">
          <Button variant="outline">Self-host it free</Button>
        </a>
      </Card>

      <p className="mt-4 font-mono text-[11px] text-white/30">
        1 credit = stock footage · 3 = AI stills · 10 = local text-to-video, each ×2 for medium
        and ×3 for long. You&apos;re quoted the exact cost before a render starts.
      </p>
    </section>
  );
}

function Feature({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <Check size={13} className="mt-0.5 shrink-0 text-accent" />
      <span>{children}</span>
    </li>
  );
}
