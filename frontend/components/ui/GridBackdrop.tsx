"use client";

import clsx from "clsx";

import { PointerLight } from "@/components/ui/PointerLight";

/**
 * The drafting surface every screen sits on.
 *
 * Three copies of the same 64px rule: the flat one, a brighter one revealed
 * only under the cursor, and a third that a slow band crosses. Each is
 * masked separately, which is why they are siblings rather than one
 * element — two mask-images on one element means the second silently
 * replaces the first.
 *
 * Fixed and full-viewport, not a band at the top of the page. It used to be
 * 640px tall and stopped somewhere around the middle of the first screen,
 * which read as half a background rather than as a surface: the thing you
 * notice is the edge, not the pattern. Fading it out downward over the
 * whole viewport means there is no edge to notice — it thins until it is
 * gone, and the page below is plain.
 *
 * It stays put while the page scrolls, deliberately. A backdrop that
 * scrolls with the content reads as wallpaper being dragged past.
 *
 * Two intensities, because it now sits under two different kinds of
 * screen. `full` is the landing and the auth pages: places you look at
 * once, where the surface is part of the pitch. `ambient` is the app —
 * the same surface, quieter, behind a screen somebody is working on for
 * half an hour.
 */
export function GridBackdrop({
  intensity = "full",
}: {
  intensity?: "full" | "ambient";
}) {
  const ambient = intensity === "ambient";

  return (
    <PointerLight
      className={clsx(
        "grid-backdrop pointer-events-none fixed inset-0 -z-10",
        // Negative z-index paints above the root background canvas and
        // below every normal-flow box, so this sits under the content
        // without the content needing a background of its own.
        ambient && "opacity-[0.55]"
      )}
    >
      {/* Under the grid, so the rule stays a drawing on top of it. */}
      <div className="bg-accent-wash absolute inset-0" aria-hidden />
      <div className="bg-grid absolute inset-0" aria-hidden />
      <div className="bg-grid-lit absolute inset-0" aria-hidden />
      {/* The 18s sweep is the one layer that draws attention on a
          schedule. On a page you read once that is ambient life; on a
          form somebody is filling in it is a light going past every
          eighteen seconds, which is a thing you start waiting for. The
          cursor light stays — it only moves when the user does. */}
      {!ambient && <div className="bg-grid-band absolute inset-0" aria-hidden />}
    </PointerLight>
  );
}
