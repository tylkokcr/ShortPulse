"use client";

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
 */
export function GridBackdrop() {
  return (
    <PointerLight className="grid-backdrop pointer-events-none fixed inset-0 -z-10">
      <div className="bg-grid absolute inset-0" aria-hidden />
      <div className="bg-grid-lit absolute inset-0" aria-hidden />
      <div className="bg-grid-band absolute inset-0" aria-hidden />
    </PointerLight>
  );
}
