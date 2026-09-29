"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { useTranslations } from "next-intl";

/**
 * One recording in, five clips out — shown rather than said.
 *
 * The strip along the top is a filmstrip of a long recording; one moment
 * in each fifth of it lights up, then lifts out as a vertical clip. After
 * a few seconds they fold back and the next recording is cut the same way.
 *
 * Every frame is a real render from `/examples`, the same files the
 * marquee plays: the strip is those five renders laid end to end, which
 * is exactly the long video an extraction would be handed, and each card
 * sits under the stretch it came from. Nothing on it is footage this
 * product did not make, and nobody else's.
 *
 * Only the middle card plays; the other four hold their poster frame.
 * Five videos decoding at once is a lot of bandwidth for a visitor who has
 * not scrolled here on purpose, and one moving card among four still ones
 * says the same thing.
 *
 * Runs only while on screen. With reduced motion it holds the first set,
 * laid out, and plays nothing.
 */
const GROUPS: string[][] = [
  ["honey", "ocean", "coffee", "leaves-de", "cats-ar"],
  ["dreams-tr", "yawn-pt", "lightning", "night-ru", "volcano"],
  ["espresso-it", "cats-tr", "sleep", "goosebumps", "moon-fr"],
];

/** Where the lit moment sits within each fifth of the strip, so the five
 *  do not look evenly spaced — real moments are not. */
const SPANS = [
  { left: 18, width: 46 },
  { left: 36, width: 38 },
  { left: 10, width: 55 },
  { left: 44, width: 34 },
  { left: 22, width: 42 },
];

/** Frames per fifth of the filmstrip. */
const FRAMES = 4;

type Phase = "strip" | "split";

const STRIP_MS = 1600;
const SPLIT_MS = 5200;

export function ClipSplit() {
  const t = useTranslations("clips.split");
  const root = useRef<HTMLDivElement>(null);
  const [group, setGroup] = useState(0);
  const [phase, setPhase] = useState<Phase>("split");
  const [running, setRunning] = useState(false);

  // Start and stop with visibility; stay still for reduced motion.
  useEffect(() => {
    const node = root.current;
    if (!node) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(
      ([entry]) => setRunning(entry.isIntersecting),
      { threshold: 0.3 }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const slugs = GROUPS[group];
  const split = phase === "split";

  // strip -> split -> (next group) strip -> ...
  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(
      () => {
        if (phase === "split") {
          setPhase("strip");
          setGroup((g) => (g + 1) % GROUPS.length);
        } else {
          setPhase("split");
        }
      },
      phase === "split" ? SPLIT_MS : STRIP_MS
    );
    return () => window.clearTimeout(timer);
  }, [running, phase]);

  return (
    <div ref={root} className="w-full" aria-hidden>
      {/* The recording. */}
      <div className="relative">
        <span className="mb-2 block font-mono text-[10px] uppercase tracking-widest text-white/30">
          {t("source")}
        </span>
        <div className="grid h-14 grid-cols-5 gap-[3px] overflow-hidden rounded-lg border border-border bg-black/40 p-[3px]">
          {slugs.map((slug, i) => (
            <div key={`${group}-${slug}`} className="relative flex gap-[2px] overflow-hidden rounded-[4px]">
              {Array.from({ length: FRAMES }, (_, f) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={f}
                  src={`/examples/${slug}.jpg`}
                  alt=""
                  loading="lazy"
                  className="h-full min-w-0 flex-1 object-cover opacity-35"
                  style={{ objectPosition: `50% ${20 + f * 20}%` }}
                />
              ))}
              {/* The moment in this stretch that becomes a clip. */}
              <span
                className={clsx(
                  "absolute inset-y-0 rounded-[3px] border-2 border-accent bg-accent/15 transition-opacity duration-500",
                  split ? "opacity-50" : "opacity-100"
                )}
                style={{ left: `${SPANS[i].left}%`, width: `${SPANS[i].width}%` }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* The clips that come out of it. */}
      <span className="mb-2 mt-5 block font-mono text-[10px] uppercase tracking-widest text-white/30">
        {t("clips")}
      </span>
      <div className="grid grid-cols-5 gap-2 sm:gap-3">
        {slugs.map((slug, i) => {
          const center = i === 2;
          return (
            <div
              key={`${group}-${slug}`}
              className={clsx(
                "relative aspect-[9/16] overflow-hidden rounded-md border bg-surface transition-all ease-out",
                center ? "border-accent/60" : "border-border",
                split
                  ? "translate-y-0 scale-100 opacity-100 duration-700"
                  : "-translate-y-16 scale-[0.35] opacity-0 duration-500"
              )}
              style={{ transitionDelay: split ? `${i * 90}ms` : "0ms" }}
            >
              {center && split && running ? (
                <video
                  src={`/examples/${slug}.mp4`}
                  poster={`/examples/${slug}.jpg`}
                  muted
                  loop
                  playsInline
                  autoPlay
                  preload="none"
                  className="h-full w-full object-cover"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`/examples/${slug}.jpg`}
                  alt=""
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
              )}
              <span className="absolute left-1.5 top-1.5 rounded bg-black/60 px-1 font-mono text-[9px] text-white/70">
                {String(i + 1).padStart(2, "0")}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
