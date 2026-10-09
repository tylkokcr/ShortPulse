"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Gift } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { getReferrals } from "@/lib/api";
import type { ReferralSummary } from "@/lib/types";
import { Card } from "@/components/ui/Card";

/** The account's invite link and its tally. Renders nothing where there
 *  is no ledger to pay into — a self-hosted install answers 404. */
export function InviteCard() {
  const t = useTranslations("invite");
  const locale = useLocale();
  const [summary, setSummary] = useState<ReferralSummary | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getReferrals()
      .then(setSummary)
      .catch(() => undefined);
  }, []);

  if (!summary) return null;
  const link = `${window.location.origin}/${locale}?ref=${summary.code}`;
  const full = summary.rewarded >= summary.cap;

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* The link is selectable on screen as well. */
    }
  }

  return (
    <Card className="surface-accent mt-8 flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent/15 text-accent">
          <Gift size={16} />
        </span>
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold">{t("title", { reward: summary.reward })}</h2>
          <p className="text-xs leading-relaxed text-white/50">
            {t("body", { reward: summary.reward, cap: summary.cap })}
          </p>
        </div>
      </div>

      <div className="flex min-w-0 items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-black/30 px-3 py-2 font-mono text-xs text-white/70 select-all">
          {link}
        </code>
        <button
          type="button"
          onClick={copy}
          className="flex shrink-0 items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs text-white/70 hover:border-border-strong hover:text-white"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {t(copied ? "copied" : "copy")}
        </button>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex gap-1">
          {Array.from({ length: summary.cap }, (_, i) => (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-full ${i < summary.rewarded ? "bg-accent" : "bg-white/10"}`}
            />
          ))}
        </div>
        <p className="text-[11px] text-white/40">
          {full
            ? t("full", { cap: summary.cap })
            : t("progress", {
                rewarded: summary.rewarded,
                cap: summary.cap,
                waiting: Math.max(0, summary.joined - summary.rewarded),
              })}
        </p>
      </div>
    </Card>
  );
}
