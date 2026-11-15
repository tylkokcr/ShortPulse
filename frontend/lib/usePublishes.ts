"use client";

import { useEffect, useState } from "react";
import { getSocialPlatforms } from "./api";

const KEY = "shortpulse:publishes";
let pending: Promise<boolean> | null = null;

function remembered(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Whether this install can publish, for the Connections link.
 *
 * Asked once per tab and remembered: the rail and the mobile menu mount
 * with every page, and each asked again — a request that, refused under a
 * busy minute, made the link vanish between two pages. A failed ask keeps
 * whatever was known before.
 */
export function usePublishes(enabled = true): boolean {
  const [publishes, setPublishes] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    if (remembered()) setPublishes(true);
    pending ??= getSocialPlatforms()
      .then((platforms) => {
        const yes = platforms.length > 0;
        try {
          sessionStorage.setItem(KEY, yes ? "1" : "0");
        } catch {
          // Private windows throw; the answer still holds for this page.
        }
        return yes;
      })
      .catch(() => {
        pending = null;
        return remembered();
      });
    pending.then((yes) => live && setPublishes(yes));
    return () => {
      live = false;
    };
  }, [enabled]);
  return publishes;
}
