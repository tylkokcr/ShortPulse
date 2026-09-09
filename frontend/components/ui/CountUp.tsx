"use client";

import { useEffect, useState } from "react";

const DURATION_MS = 900;

/**
 * Counts a number up on first paint, and does nothing at all to anything
 * that isn't one.
 *
 * The stats row mixes "9" with "MIT", so this takes the displayed string
 * and only animates it when it parses cleanly as an integer. Anything else
 * is rendered untouched — no parsing surprises, no "NaN" appearing where a
 * licence name should be.
 *
 * Initial state is the *final* value, not zero: server-rendered HTML and a
 * no-JS client then show the real number, and the only cost of the
 * animation never running is that the number was already there.
 */
export function CountUp({ value, className }: { value: string; className?: string }) {
  const numeric = /^\d+$/.test(value) ? Number(value) : null;
  const [shown, setShown] = useState(value);

  useEffect(() => {
    if (numeric === null) return;
    if (typeof window === "undefined" || !window.matchMedia) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (typeof document !== "undefined" && document.visibilityState !== "visible") return;

    let frame = 0;
    const started = performance.now();

    function step(now: number) {
      const t = Math.min(1, (now - started) / DURATION_MS);
      // Same curve as the entrance animations, so the number settling and
      // the panel arriving feel like one motion rather than two.
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(String(Math.round(eased * (numeric as number))));
      if (t < 1) frame = window.requestAnimationFrame(step);
    }

    setShown("0");
    frame = window.requestAnimationFrame(step);
    return () => {
      window.cancelAnimationFrame(frame);
      // Whatever happened, leave the real value behind.
      setShown(value);
    };
  }, [numeric, value]);

  return <span className={className}>{shown}</span>;
}
