"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Coins, LogOut } from "lucide-react";
import { getCredits } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { useAuth } from "./AuthProvider";

/**
 * Signed-in identity and credit balance.
 *
 * Renders nothing when the backend reports `enabled: false` — a
 * self-hosted install has no accounts and no billing, and showing a
 * balance of zero there would read as "you're out of credits" rather than
 * "this is free".
 *
 * `compact` drops the address and the sign-out button, for the app shell,
 * where the rail already carries both. It still mounts: the effect below
 * is what puts the balance in the store, and the rail's own Credits entry
 * is drawn from it — hiding this component instead of narrowing it would
 * take that link with it.
 */
export function AccountBar({ compact = false }: { compact?: boolean }) {
  const { session, enabled, signOut } = useAuth();
  const { credits, setCredits } = useShortPulseStore();
  const t = useTranslations("nav");

  useEffect(() => {
    if (!enabled || !session) return;
    getCredits().then(setCredits).catch(console.error);
  }, [enabled, session, setCredits]);

  if (!enabled || !session || !credits?.enabled) return null;

  return (
    <div className="flex items-center justify-between gap-4 text-xs">
      {/* Hidden on a phone: at 390px the address plus the balance plus
          the sign-out button overflow the header by 25px and the whole
          page scrolls sideways. The balance is the useful part; who you
          are signed in as is not worth a horizontal scrollbar. */}
      {!compact && (
        <span className="hidden truncate text-white/40 sm:block">{session.user.email}</span>
      )}
      <div className="flex items-center gap-3">
        {/* The balance is also the way to top it up — otherwise there is
            nowhere in the app to buy credits, only the landing page's
            pricing section, which signed-in users never see. */}
        <Link
          href="/credits"
          title={t("creditsRemaining")}
          className="flex items-center gap-1.5 text-white/70 transition-colors hover:text-accent"
        >
          <Coins size={13} />
          {credits.balance}
        </Link>
        {!compact && (
          <button
            onClick={signOut}
            className="flex items-center gap-1 text-white/40 hover:text-white/80"
          >
            <LogOut size={13} />
            {t("signOut")}
          </button>
        )}
      </div>
    </div>
  );
}
