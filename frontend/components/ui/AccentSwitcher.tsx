"use client";

import { useEffect, useState, type CSSProperties } from "react";
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
      className={clsx("flex items-center gap-2", className)}
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
              "h-3.5 w-3.5 rounded-full transition-[transform,box-shadow,opacity] duration-200",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              // Selection is a halo in the swatch's own colour and a small
              // step up in size, not a grey ring with a gap in it — that
              // read as a foreign object sitting on top of the colour, and
              // it was the widest thing in the header. Both cues are drawn
              // outside the layout box (a shadow and a transform), so the
              // row stays put; the earlier comment's worry about growing
              // the dot applied to width, not to scale.
              //
              // Size and opacity carry the state as well as hue does, so
              // the marked dot is still findable without colour vision.
              selected
                ? "scale-[1.18] ring-[3px]"
                : "opacity-80 hover:scale-110 hover:opacity-100",
              // Before hydration nothing is marked, so nothing lies.
              accent === null && "opacity-80"
            )}
            // The ring colour is the swatch's own, at a third strength and
            // with no offset, so it hugs the dot as a halo. Set as the ring
            // variable rather than a literal box-shadow because Tailwind
            // composes focus-visible's ring through the same property — an
            // inline box-shadow here would silently delete the focus ring.
            style={
              {
                backgroundColor: swatch,
                "--tw-ring-color": `${swatch}59`,
              } as CSSProperties
            }
          />
        );
      })}
    </div>
  );
}
