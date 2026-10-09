"use client";

import { useEffect, useRef } from "react";
import { TURNSTILE_SITE_KEY } from "@/lib/turnstile";

/**
 * Cloudflare Turnstile, the bot check in front of the email ways in.
 *
 * Every new account is given credits that cost real money to spend, so an
 * address made by a script is a bill. Supabase checks the token itself
 * (Authentication → Bot and Abuse Protection), which is why there is no
 * server code for this: the token rides along with signUp, signIn, the
 * sign-in link and the reset, and Supabase refuses any of them without a
 * fresh one.
 *
 * Off when NEXT_PUBLIC_TURNSTILE_SITE_KEY is unset — a self-hosted install
 * has no credits to protect, and its sign-in screen stays as it was. Turn
 * it on here before turning it on in Supabase, or every email sign-in
 * fails in between.
 *
 * "interaction-only": most people never see it; it appears only when
 * Cloudflare wants a click. No cookies, and the script loads on the sign-in
 * screen alone, not on every page.
 */

const SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

interface TurnstileApi {
  render(
    element: HTMLElement,
    options: {
      sitekey: string;
      callback: (token: string) => void;
      "expired-callback": () => void;
      "error-callback": () => void;
      theme: "dark";
      appearance: "interaction-only";
      size: "flexible";
    }
  ): string;
  remove(id: string): void;
}

let loading: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  const ready = (window as { turnstile?: TurnstileApi }).turnstile;
  if (ready) return Promise.resolve(ready);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_URL;
      script.async = true;
      script.onload = () => {
        const api = (window as { turnstile?: TurnstileApi }).turnstile;
        if (api) resolve(api);
        else reject(new Error("Turnstile did not load"));
      };
      script.onerror = () => {
        loading = null; // let the next mount try again
        reject(new Error("Turnstile did not load"));
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

/**
 * Hands a token to `onToken`, and null when it expires or fails. A token
 * is good for one request: change `round` after each one and the widget
 * is rebuilt for a fresh token.
 */
export function Turnstile({ onToken, round }: { onToken: (token: string | null) => void; round: number }) {
  const box = useRef<HTMLDivElement>(null);
  const report = useRef(onToken);
  useEffect(() => {
    report.current = onToken;
  }, [onToken]);

  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || !box.current) return;
    let id: string | null = null;
    let live = true;
    report.current(null);
    loadTurnstile()
      .then((api) => {
        if (!live || !box.current) return;
        id = api.render(box.current, {
          sitekey: TURNSTILE_SITE_KEY,
          callback: (token) => report.current(token),
          "expired-callback": () => report.current(null),
          "error-callback": () => report.current(null),
          theme: "dark",
          appearance: "interaction-only",
          size: "flexible",
        });
      })
      .catch(() => undefined);
    return () => {
      live = false;
      const api = (window as { turnstile?: TurnstileApi }).turnstile;
      if (id && api) api.remove(id);
    };
  }, [round]);

  if (!TURNSTILE_SITE_KEY) return null;
  return <div ref={box} />;
}
