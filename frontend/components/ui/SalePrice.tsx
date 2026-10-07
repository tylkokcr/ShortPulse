"use client";

import { useFormatter, useTranslations } from "next-intl";
import { formatPrice } from "@/lib/money";
import type { CreditPack } from "@/lib/types";

/**
 * What a pack's price is reduced from, while a sale runs: the regular
 * price struck through, the saving, and the line EU price rules require
 * beside any reduction — the lowest price of the 30 days before it. The
 * server only sends a regular price when that is true of it (see
 * credits.SALE), so this renders nothing outside a sale.
 */
export function SaleOff({ pack, currency }: { pack: CreditPack; currency?: string }) {
  if (!pack.regular_price_cents || pack.regular_price_cents <= pack.price_cents) return null;
  const off = Math.round((1 - pack.price_cents / pack.regular_price_cents) * 100);
  return (
    <span className="flex items-center gap-2 text-sm">
      <s className="text-white/40">{formatPrice(pack.regular_price_cents, currency)}</s>
      <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-accent">
        −{off}%
      </span>
    </span>
  );
}

export function SaleNote({ pack, currency }: { pack: CreditPack; currency?: string }) {
  const t = useTranslations("sale");
  const format = useFormatter();
  if (!pack.regular_price_cents || pack.regular_price_cents <= pack.price_cents) return null;
  return (
    <p className="text-[11px] leading-snug text-white/35">
      {t("lowest", { price: formatPrice(pack.regular_price_cents, currency) })}
      {pack.sale_ends_at &&
        ` ${t("ends", { date: format.dateTime(new Date(pack.sale_ends_at), { day: "numeric", month: "long" }) })}`}
    </p>
  );
}
