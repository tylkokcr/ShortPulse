"use client";

import { useEffect, useState } from "react";
import { Check, Sparkles, Github } from "lucide-react";
import { useTranslations } from "next-intl";
import clsx from "clsx";
import { SIGNUP_CREDITS } from "@/lib/signupCredits";
import { getPublicPricing } from "@/lib/api";
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

/** Which pack ids have written copy. A deployment is free to define its
 *  own — the card falls back to the id and no blurb, exactly as before,
 *  rather than throwing on a missing message. */
const LABELLED_PACKS = new Set(["starter", "creator", "studio"]);

/** Cheapest real render (stock_media + short) costs 1 credit; the default
 *  fast_hybrid short costs 3. Quoting both keeps "how many videos" honest
 *  instead of advertising only the flattering number.
 *
 *  `standard` is dropped where fast_hybrid can't run at all — no diffusion
 *  stack and no image API — because quoting videos in a mode the
 *  deployment refuses to sell is an advertisement for a product that
 *  doesn't exist here. */
function videosFor(credits: number, generatedStills: boolean) {
  return {
    basic: credits,
    standard: generatedStills ? Math.floor(credits / 3) : null,
  };
}

export function Pricing() {
  const t = useTranslations("pricing");
  const [packs, setPacks] = useState<CreditPack[]>(FALLBACK_PACKS);
  // Currency and whether VAT is already in the price are deployment
  // settings, so they come from the server alongside the packs.
  const [currency, setCurrency] = useState("usd");
  const [taxIncluded, setTaxIncluded] = useState(false);
  // Assumed until the server says otherwise, so the copy doesn't visibly
  // rewrite itself on a deployment where it is true.
  //
  // Two flags, not one. They used to be the same boolean because the modes
  // that needed a GPU stood or fell together; fast_hybrid now runs over an
  // API without one and ai_video still doesn't, so a single flag would
  // print a price for local text-to-video the moment AI stills went live —
  // an offer this deployment refuses at the point of sale.
  const [generatedStills, setGeneratedStills] = useState(true);
  const [localVideo, setLocalVideo] = useState(true);
  // What a signup is actually worth here. Server-driven for the same
  // reason as the packs: it is a setting, and it has already changed.
  const [signupCredits, setSignupCredits] = useState(SIGNUP_CREDITS);
  // Whether this deployment can take money at all — it needs both a ledger
  // to record credits in and Stripe to charge through. Optimistic for the
  // same reason as FALLBACK_PACKS: if the API is unreachable, a shop window
  // that stays up is better than one that empties itself.
  const [sold, setSold] = useState(true);

  useEffect(() => {
    // Not getCredits(): a visitor has no account, and a deployment with
    // REQUIRE_AUTH answers that 401. The catch below would swallow it and
    // the page would advertise the USD fallback while the checkout took
    // euros including VAT.
    getPublicPricing()
      .then((pricing) => {
        if (pricing.packs?.length) setPacks(pricing.packs);
        if (pricing.currency) setCurrency(pricing.currency);
        setTaxIncluded(Boolean(pricing.tax_included));
        if (pricing.modes) {
          setGeneratedStills(pricing.modes.includes("fast_hybrid"));
          setLocalVideo(pricing.modes.includes("ai_video"));
        }
        if (pricing.signup_credits) setSignupCredits(pricing.signup_credits);
        setSold(Boolean(pricing.sold));
      })
      .catch(() => {
        /* Keep the fallback — see FALLBACK_PACKS. */
      });
  }, []);

  return (
    <section id="pricing" className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">
          {t("eyebrow")}
        </span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
        <p className="max-w-xl text-sm text-white/50">{t("intro")}</p>
      </div>

      {/* Four across only when there are packs to put there; alone, the free
          tier gets a card's width rather than the whole section. */}
      <div className={clsx("grid grid-cols-1 gap-4", sold ? "lg:grid-cols-4" : "max-w-sm")}>
        <Card className="flex flex-col gap-4 bg-surface-raised">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">{t("free.name")}</h3>
            <p className="text-xs text-white/40">{t("free.blurb")}</p>
          </div>
          <div className="flex items-baseline gap-1.5">
            {/* Formatted, not written: on a EUR deployment a hardcoded
                "$0" sits directly above three prices in euros. */}
            <span className="text-3xl font-semibold tracking-tight">
              {formatPrice(0, currency)}
            </span>
          </div>
          {/* What the grant buys, not what the deployment can render.
              Those were the same thing until the signup credits were
              limited to stock footage — see credits.FREE_TIER_MODES — and
              this card kept quoting "5 standard videos" for a mode the API
              now refuses to sell an unpaid account. `generatedStills` still
              decides whether AI stills are mentioned at all, because a
              deployment without them must not advertise an upgrade it
              cannot deliver either.

              The AI-stills line is the offer, so it goes above the stock
              one: a visitor deciding whether to sign up is deciding
              whether the paid mode is any good, and this card is where
              they are told they can find out without paying. It is free
              of *purchase*, not free of charge — the grant pays for it
              like any other render, which is why the credit line stays
              first and the count below it is what remains after. */}
          <ul className="flex flex-col gap-2 text-xs text-white/50">
            <Feature>{t("free.credits", { credits: signupCredits })}</Feature>
            {generatedStills && <Feature>{t("free.firstAiFree")}</Feature>}
            {/* Two whole sentences rather than a "Then" glued to the front
                of one: the word that changes is not at the start in every
                language, and in some it changes the rest of the line. */}
            <Feature>{generatedStills ? t("free.thenStock") : t("free.stockOnly")}</Feature>
            <Feature>{t("free.everyLanguage")}</Feature>
            <Feature>{t("free.noWatermark")}</Feature>
          </ul>
          <a href="#sign-in" className="mt-auto pt-2">
            <Button variant="secondary" className="w-full">
              {t("free.cta")}
            </Button>
          </a>
        </Card>

        {/* A deployment that cannot charge shows no prices. The API still
            serves the pack list — it is the same tariff a self-hoster reads
            to understand what a credit is worth — but rendering it here as
            three cards with a call to action offers a purchase that
            `POST /api/credits/checkout` answers 503. */}
        {sold && packs.map((pack) => {
          const labelled = LABELLED_PACKS.has(pack.id);
          const name = labelled ? t(`packs.${pack.id}.name`) : pack.id;
          const blurb = labelled ? t(`packs.${pack.id}.blurb`) : "";
          const { basic, standard } = videosFor(pack.credits, generatedStills);
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
                  {t("popular")}
                </Badge>
              )}

              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-semibold">{name}</h3>
                <p className="text-xs text-white/40">{blurb}</p>
              </div>

              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-semibold tracking-tight">
                  {formatPrice(pack.price_cents, currency)}
                  {taxIncluded && (
                    <span className="ml-1.5 align-middle text-[10px] font-normal text-white/30">
                      {t("taxIncluded")}
                    </span>
                  )}
                </span>
                <span className="text-xs text-white/40">{t("oneOff")}</span>
              </div>

              <ul className="flex flex-col gap-2 text-xs text-white/50">
                <Feature>
                  <span className="text-white/80">
                    {t("packCredits", { credits: pack.credits })}
                  </span>
                </Feature>
                {standard !== null && (
                  <Feature>{t("standardVideos", { count: standard })}</Feature>
                )}
                <Feature>{t("stockVideos", { count: basic })}</Feature>
                <Feature>{t("neverExpire")}</Feature>
              </ul>

              <a href="#sign-in" className="mt-auto pt-2">
                <Button variant={pack.popular ? "gradient" : "secondary"} className="w-full">
                  {t("packCta", { credits: pack.credits })}
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
            {t("selfHost.title")}
          </h3>
          <p className="text-xs text-white/50">{t("selfHost.body")}</p>
        </div>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="shrink-0">
          <Button variant="outline">{t("selfHost.cta")}</Button>
        </a>
      </Card>

      {/* The tariff, and so it lists what can actually be bought here. The
          feature copy above still describes all three engines, because
          self-hosting is offered on this same page and they all work
          there — but a price for a mode this deployment refuses to sell
          is an offer it cannot honour. */}
      {/* Built by joining whole phrases with a separator, not by gluing
          fragments onto a sentence: " · 3 = AI stills" concatenated mid-line
          assumes an English word order that three of the four languages
          here do not share. */}
      <p className="mt-4 font-mono text-[11px] text-white/30">
        {t("tariff.note", {
          rates: [
            t("tariff.stock"),
            generatedStills ? t("tariff.aiStills") : null,
            localVideo ? t("tariff.localVideo") : null,
          ]
            .filter(Boolean)
            .join(" · "),
        })}
      </p>

      {/* For the visitor who arrived from somewhere these prices are not
          the local money. The hesitation happens here, looking at the
          cards, not at the checkout — so the answer belongs here too.

          It says what is true today. Stripe Adaptive Pricing would make it
          "you'll see your local currency at checkout", but that needs the
          price currency to be one of the account's settlement currencies
          and this one settles elsewhere, so the page would be promising a
          checkout the deployment does not currently produce. Swap the
          second sentence the day it is switched on, not before.

          Only alongside real prices: with no Stripe there is nothing here
          to be in a currency at all. */}
      {sold && (
        <p className="mt-1 font-mono text-[11px] text-white/30">
          {t("currencyNote", { currency: currency.toUpperCase() })}
        </p>
      )}
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
