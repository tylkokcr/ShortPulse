"use client";

import { useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { usePathname } from "@/i18n/navigation";
import clsx from "clsx";
import { ACCENT_STORAGE_KEY } from "./accentBoot";

/**
 * Which colour plays the accent.
 *
 * The design's rule is one accent, used only for the thing you should look
 * at. This lets a visitor choose *which* colour that is; it does not let
 * them add a second one, and there is deliberately no "off". Every option
 * clears 6:1 against black because Button's primary variant prints black
 * text on the accent — see the palettes in globals.css.
 *
 * Green is missing on purpose: #4ade80 means "a render is live" here, and
 * an accent wearing it would make decoration look like machinery.
 */
export const ACCENTS = [
  { id: "ember", label: "Ember", swatch: "#ff5c1a" },
  { id: "amber", label: "Amber", swatch: "#f5a524" },
  { id: "rose", label: "Rose", swatch: "#ff5c7a" },
  { id: "iris", label: "Iris", swatch: "#a78bfa" },
  { id: "cyan", label: "Cyan", swatch: "#22d3ee" },
] as const;

export type AccentId = (typeof ACCENTS)[number]["id"];

/** Writes the choice onto <html>, where the CSS variables hang off it.
 *  "ember" is the default in :root, so it is an absence rather than a
 *  value — setting data-accent="ember" would work too, but removing it
 *  keeps the attribute meaning "something other than the default". */
function applyAccent(id: AccentId) {
  const root = document.documentElement;
  if (id === "ember") root.removeAttribute("data-accent");
  else root.setAttribute("data-accent", id);
}

export function AccentSwitcher({ className }: { className?: string }) {
  // Starts as null rather than "ember" so the first paint after hydration
  // doesn't mark the wrong dot as selected for a frame.
  const [accent, setAccent] = useState<AccentId | null>(null);

  // Re-applied on every navigation, not just read.
  //
  // accentBoot's script covers full loads, before React exists. It does
  // not run on a soft navigation, and that navigation re-renders <html>
  // from the server, where the attribute does not exist — so this puts
  // it back.
  //
  // Keyed on the locale as well as the path because next-intl's
  // usePathname strips the prefix: going from / to /tr reports "/" both
  // times, and an effect watching only the path would never re-run on
  // the one navigation a language switch actually performs.
  const pathname = usePathname();
  const locale = useLocale();
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(ACCENT_STORAGE_KEY);
    } catch {
      // Private windows and blocked site data both throw on read. The
      // page still works; it just doesn't remember.
    }
    const id = (ACCENTS.find((a) => a.id === stored)?.id ?? "ember") as AccentId;
    setAccent(id);
    applyAccent(id);
  }, [pathname, locale]);

  function choose(id: AccentId) {
    setAccent(id);
    applyAccent(id);
    try {
      localStorage.setItem(ACCENT_STORAGE_KEY, id);
    } catch {
      // Same as above — the choice applies for this page either way.
    }
  }

  return (
    <div
      className={clsx("flex items-center gap-1.5", className)}
      role="radiogroup"
      aria-label="Accent colour"
    >
      {ACCENTS.map(({ id, label, swatch }) => {
        const selected = accent === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={label}
            title={label}
            onClick={() => choose(id)}
            className={clsx(
              "h-3.5 w-3.5 rounded-full transition-[transform,box-shadow] duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              // The ring, not a size change, marks the selection: growing
              // the dot would shift the two beside it every time.
              selected ? "ring-2 ring-white/70 ring-offset-2 ring-offset-background" : "hover:scale-110",
              // Before hydration nothing is marked, so nothing lies.
              accent === null && "opacity-60"
            )}
            style={{ backgroundColor: swatch }}
          />
        );
      })}
    </div>
  );
}
