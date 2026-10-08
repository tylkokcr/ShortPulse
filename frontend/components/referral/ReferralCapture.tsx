"use client";

import { useEffect } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { claimReferral } from "@/lib/api";

const KEY = "shortpulse.ref";

function read(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function write(code: string | null) {
  try {
    if (code) window.localStorage.setItem(KEY, code);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* Private mode: the link still works if they sign in from this page. */
  }
}

/**
 * Remembers the invite code a visitor arrived with (`?ref=`) across the
 * Google sign-in round trip, and hands it to the server once they have an
 * account. The server decides whether it counts — a new account, not the
 * inviter's own, no earlier inviter — so this only ever reports it once
 * and forgets it, whatever the answer.
 */
export function ReferralCapture() {
  const { session } = useAuth();

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("ref");
    if (code && /^[a-z0-9]{4,32}$/i.test(code)) write(code.toLowerCase());
  }, []);

  useEffect(() => {
    if (!session) return;
    const code = read();
    if (!code) return;
    write(null);
    claimReferral(code).catch(() => undefined);
  }, [session]);

  return null;
}
