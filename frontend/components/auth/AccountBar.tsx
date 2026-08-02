"use client";

import { useEffect } from "react";
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
 */
export function AccountBar() {
  const { session, enabled, signOut } = useAuth();
  const { credits, setCredits } = useShortPulseStore();

  useEffect(() => {
    if (!enabled || !session) return;
    getCredits().then(setCredits).catch(console.error);
  }, [enabled, session, setCredits]);

  if (!enabled || !session || !credits?.enabled) return null;

  return (
    <div className="flex items-center justify-between gap-4 text-xs">
      <span className="truncate text-white/40">{session.user.email}</span>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-white/70" title="Credits remaining">
          <Coins size={13} />
          {credits.balance}
        </span>
        <button
          onClick={signOut}
          className="flex items-center gap-1 text-white/40 hover:text-white/80"
        >
          <LogOut size={13} />
          Sign out
        </button>
      </div>
    </div>
  );
}
