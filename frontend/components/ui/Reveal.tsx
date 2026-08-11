"use client";

import { useEffect, useRef, useState, type HTMLAttributes } from "react";

interface RevealProps extends HTMLAttributes<HTMLDivElement> {
  delay?: number;
}

/** How long to wait for the observer to prove it works before giving up
 *  and showing everything. IntersectionObserver delivers an initial
 *  callback for each observed element almost immediately, so silence past
 *  this means callbacks aren't being delivered at all. */
const OBSERVER_GRACE_MS = 1000;

/**
 * Fades and lifts a section in the first time it scrolls into view.
 *
 * Built so it cannot hide content permanently, which is the failure mode
 * that makes scroll animations dangerous:
 *
 *  - The hidden state is only applied after mount, so server-rendered
 *    markup and a no-JavaScript client both show everything.
 *  - If IntersectionObserver is missing, nothing is ever hidden.
 *  - If the observer exists but never delivers a callback — which happens
 *    in backgrounded or non-composited tabs, and is exactly what a
 *    headless browser looks like — the grace timer reveals everything.
 *    Without it a whole landing page can render as blank panels.
 *
 * `threshold: 0` matters too: these sections are often taller than the
 * viewport, and a percentage threshold on an element you can never see all
 * of is a trap.
 *
 * `delay` staggers items in a row or grid. It waits before switching to
 * the shown state rather than setting an animation-delay, so the element
 * stays in the hidden state throughout the wait. Doing it in CSS would
 * need `animation-fill-mode: backwards` to avoid a flash of the finished
 * state during the delay — and fill-mode is exactly what pins content
 * invisible when the animation never advances, which is the failure this
 * component exists to avoid.
 */
export function Reveal({ className, style, delay = 0, children, ...props }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"initial" | "hidden" | "shown">("initial");

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setState("shown");
      return;
    }

    // A background tab (cmd-click, "open in new tab", a restored session)
    // has a frozen animation timeline: animations report `running` while
    // their currentTime stays at 0 forever. Anything whose visibility
    // depends on one is then invisible until the tab is focused. Skipping
    // the choreography entirely leaves the section in its natural, visible
    // state — there is no entrance to watch in a tab nobody is looking at.
    if (typeof document !== "undefined" && document.visibilityState !== "visible") {
      return;
    }

    setState("hidden");

    let delivered = false;
    let stagger: number | undefined;

    const observer = new IntersectionObserver(
      ([entry]) => {
        delivered = true;
        if (entry.isIntersecting) {
          observer.disconnect();
          if (delay) {
            stagger = window.setTimeout(() => setState("shown"), delay);
          } else {
            setState("shown");
          }
        }
      },
      { threshold: 0, rootMargin: "0px 0px -40px 0px" }
    );
    observer.observe(node);

    const grace = window.setTimeout(() => {
      if (!delivered) {
        setState("shown");
        observer.disconnect();
      }
    }, OBSERVER_GRACE_MS);

    return () => {
      window.clearTimeout(grace);
      if (stagger) window.clearTimeout(stagger);
      observer.disconnect();
    };
  }, [delay]);

  return (
    <div
      ref={ref}
      data-reveal={state === "initial" ? undefined : state}
      className={className}
      style={style}
      {...props}
    >
      {children}
    </div>
  );
}
