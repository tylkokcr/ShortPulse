"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * Writes the pointer position onto a container as --mx/--my, for
 * .bg-grid-lit to light the blueprint grid with.
 *
 * Everything about it is designed to be absent rather than degraded:
 *
 *  - Nothing is written until a pointer actually moves, and the CSS
 *    defaults put the light off-screen, so a page that never runs this —
 *    no JS, a crawler, a print — looks exactly like it did before.
 *  - Coarse pointers are skipped entirely. A finger is not a cursor: the
 *    light would only ever appear under a tap, which is both useless and
 *    the moment the finger is covering it.
 *  - prefers-reduced-motion is honoured. A light that chases the cursor is
 *    motion whether or not it uses a keyframe.
 *
 * Positions are stored on a ref and flushed inside one rAF, so a fast
 * mouse across the hero costs one style write per frame instead of one per
 * pointermove event.
 */
export function PointerLight({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof window === "undefined" || !window.matchMedia) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(pointer: fine)").matches) return;

    let frame = 0;
    let next: { x: number; y: number } | null = null;

    // The rect is read inside the frame, not on every event: the layer
    // this lights is usually pointer-events:none and often behind the
    // content, so listening on the window and converting is the only way
    // to see the cursor at all — and once per frame is cheap enough.
    function flush() {
      frame = 0;
      if (!next || !node) return;
      const box = node.getBoundingClientRect();
      node.style.setProperty("--mx", `${next.x - box.left}px`);
      node.style.setProperty("--my", `${next.y - box.top}px`);
    }

    function onMove(event: PointerEvent) {
      next = { x: event.clientX, y: event.clientY };
      if (!frame) frame = window.requestAnimationFrame(flush);
    }

    // Leaving the document puts the light back where the CSS default has
    // it rather than freezing it wherever the cursor happened to exit — a
    // bright patch stuck at the edge is more distracting than no light.
    function onLeave() {
      if (!node) return;
      node.style.removeProperty("--mx");
      node.style.removeProperty("--my");
    }

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
