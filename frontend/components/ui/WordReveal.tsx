"use client";

import { Children, isValidElement, useEffect, useState, type ReactNode } from "react";

/** Milliseconds between two words. Matches the delay step in globals.css;
 *  the two have to agree for the grace timer below to be long enough. */
const STEP_MS = 55;
const DURATION_MS = 550;

/**
 * Reveals a headline a word at a time.
 *
 * The words are split here rather than in the caller so the markup stays
 * one readable sentence, and so `<span className="text-accent-emphasis">`
 * inside it keeps working — an element child is emitted whole and counts
 * as a single step rather than being torn apart.
 *
 * The safety contract is the one [data-reveal] uses, because a headline is
 * the worst possible thing to leave invisible:
 *
 *  - Server-rendered markup and a no-JS client get plain, visible words.
 *  - Nothing animates in a tab that isn't visible; a frozen animation
 *    timeline there would hold every word at opacity 0 until focus.
 *  - The animating attribute is removed on a timer sized to the whole
 *    sequence, so even if no frame ever advances the text ends up visible.
 */
export function WordReveal({
  children,
  className,
  as: Tag = "h1",
}: {
  children: ReactNode;
  className?: string;
  as?: "h1" | "h2" | "p";
}) {
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (typeof document !== "undefined" && document.visibilityState !== "visible") return;

    setRunning(true);
    const total = DURATION_MS + STEP_MS * 40 + 400;
    const stop = window.setTimeout(() => setRunning(false), total);
    return () => window.clearTimeout(stop);
  }, []);

  // One flat list, so the delay index counts across the whole headline
  // rather than restarting inside each nested element.
  let index = 0;
  const parts: ReactNode[] = [];

  function push(node: ReactNode, key: string) {
    if (typeof node === "string") {
      node.split(/(\s+)/).forEach((chunk, i) => {
        if (!chunk) return;
        if (/^\s+$/.test(chunk)) {
          parts.push(<span key={`${key}-s${i}`}> </span>);
          return;
        }
        parts.push(
          <span
            key={`${key}-w${i}`}
            className="word inline-block"
            style={{ "--i": index++ } as React.CSSProperties}
          >
            {chunk}
          </span>
        );
      });
      return;
    }
    if (isValidElement(node)) {
      parts.push(
        <span
          key={key}
          className="word inline-block"
          style={{ "--i": index++ } as React.CSSProperties}
        >
          {node}
        </span>
      );
      return;
    }
    if (node !== null && node !== undefined && node !== false) parts.push(node);
  }

  Children.toArray(children).forEach((child, i) => push(child, `c${i}`));

  return (
    <Tag className={className} data-words={running ? "run" : undefined}>
      {parts}
    </Tag>
  );
}
