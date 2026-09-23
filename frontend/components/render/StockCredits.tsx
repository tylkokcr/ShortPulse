"use client";

import { Check, Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import type { ScriptOutput, StockAttribution } from "@/lib/types";

/**
 * Credits for the stock footage in a render.
 *
 * This is a licence condition, not decoration: Pexels' API terms require a
 * visible link back to Pexels from any application using their API, and
 * crediting the photographer where possible. It renders whenever a project
 * used stock footage, and nothing about it is dismissible.
 *
 * The copy button exists because the requirement doesn't travel with the
 * file — someone posting the video to TikTok needs the credit line in their
 * description, and they won't retype it.
 */
export function StockCredits({ script }: { script: ScriptOutput }) {
  const [copied, setCopied] = useState(false);

  const t = useTranslations("app.stockCredits");
  const credits = dedupe(
    script.scenes
      .map((scene) => scene.visual.attribution)
      .filter((c): c is StockAttribution => Boolean(c))
  );

  if (credits.length === 0) return null;

  const providers = Array.from(new Set(credits.map((c) => c.provider)));
  const plainText = credits.map(creditLine).join("\n");

  async function copy() {
    await navigator.clipboard.writeText(plainText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-medium text-white/60">
          {t("footageFrom")}
          {providers.map((provider, i) => {
            const url = credits.find((c) => c.provider === provider)!.provider_url;
            return (
              <span key={provider}>
                {i > 0 && t("and")}
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-white/80 underline underline-offset-2 hover:text-white"
                >
                  {provider}
                </a>
              </span>
            );
          })}
        </h4>
        <button
          onClick={copy}
          className="flex shrink-0 items-center gap-1 text-xs text-white/40 hover:text-white/80"
          title={t("copyTitle")}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? t("copied") : t("copy")}
        </button>
      </div>

      <ul className="flex flex-col gap-0.5">
        {credits.map((credit) => (
          <li key={creditLine(credit)} className="text-xs text-white/40">
            {credit.author ? (
              t.rich("videoBy", {
                author: () => <Linked href={credit.author_url}>{credit.author}</Linked>,
                provider: () => (
                  <Linked href={credit.source_url ?? credit.provider_url}>
                    {credit.provider}
                  </Linked>
                ),
              })
            ) : (
              t.rich("videoFrom", {
                provider: () => <Linked href={credit.provider_url}>{credit.provider}</Linked>,
              })
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Linked({ href, children }: { href?: string | null; children: React.ReactNode }) {
  if (!href) return <>{children}</>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-2 hover:text-white/70"
    >
      {children}
    </a>
  );
}

function creditLine(credit: StockAttribution): string {
  return credit.author
    ? `Video by ${credit.author} on ${credit.provider}`
    : `Video from ${credit.provider}`;
}

/** The same photographer often supplies several scenes; credit them once. */
function dedupe(credits: StockAttribution[]): StockAttribution[] {
  const seen = new Map<string, StockAttribution>();
  for (const credit of credits) {
    const key = `${credit.provider}:${credit.author ?? ""}`;
    if (!seen.has(key)) seen.set(key, credit);
  }
  return Array.from(seen.values());
}
