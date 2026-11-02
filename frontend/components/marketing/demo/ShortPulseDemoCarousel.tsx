"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import s from "./ShortPulseDemoCarousel.module.css";
import ShortPulseDemo, { SHORTPULSE_DEMO_LENGTH, type ShortPulseDemoAssets } from "./ShortPulseDemo";
import CaptionDemo, { CAPTION_DEMO_LENGTH, type CaptionDemoAssets } from "./CaptionDemo";
import EditDemo, { EDIT_DEMO_LENGTH, type EditDemoAssets } from "./EditDemo";
import { SHELL, type Locale } from "./kit";

/**
 * The three Studio modes as one slider: Generate from a topic → Caption or
 * dub my video → Edit my clips. Each demo plays through once, then the next
 * slides in. Tabs jump, arrows step, and on touch screens you can swipe.
 */

export type ShortPulseCarouselAssets = {
  generate: ShortPulseDemoAssets;
  caption: CaptionDemoAssets;
  edit: EditDemoAssets;
};

type Props = {
  assets: ShortPulseCarouselAssets;
  locale?: Locale;
  accent?: string;
  className?: string;
  /** Which slide to open on. */
  start?: 0 | 1 | 2;
};

const LENGTHS = [SHORTPULSE_DEMO_LENGTH, CAPTION_DEMO_LENGTH, EDIT_DEMO_LENGTH];
/** Frames shown while a slide is waiting off to the side, and for reduced motion. */
const POSTER = [600, 600, 600];
const STILL = [13300, 12400, 15000];

const ICONS = [
  <path key="w" d="m15 4 1.5 1.5M19.5 8.5 21 10M14 8l-11 11 2 2 11-11zM18 3v2M22 7h-2M20 2l-1 1" />,
  <path key="u" d="M12 16V4M7 9l5-5 5 5M5 20h14" />,
  <g key="s">
    <circle cx="6" cy="6" r="3" />
    <circle cx="6" cy="18" r="3" />
    <path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12" />
  </g>,
];

function Svg({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {children}
    </svg>
  );
}

export default function ShortPulseDemoCarousel({ assets, locale = "en", accent = "rgb(var(--accent))", className, start = 0 }: Props) {
  const [active, setActive] = useState<number>(start);
  const [t, setT] = useState(0);
  const [reduced, setReduced] = useState(false);
  // Drawn on the client only. The demos compute their frames with
  // Math.sin and friends, whose last digits differ between the server's V8
  // and the browser's, so a server render never hydrated cleanly (a
  // waveform bar of 44.1539% against 44.1539170234024%). Nothing in them
  // is content a crawler needs; the section heading above says it.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  const [drag, setDrag] = useState<number | null>(null);
  // The frame each slide shows while it waits off to the side. State, not
  // a ref: it is read during render, which a ref must not be.
  const [held, setHeld] = useState<number[]>([...POSTER]);
  const rootRef = useRef<HTMLDivElement>(null);
  const tRef = useRef(0);
  const activeRef = useRef(active);
  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  const hold = useCallback((i: number, at: number) => {
    setHeld((prev) => prev.map((v, k) => (k === i ? at : v)));
  }, []);

  const go = useCallback(
    (i: number) => {
      const n = ((i % 3) + 3) % 3;
      if (n === activeRef.current) return;
      hold(activeRef.current, tRef.current); // the one leaving keeps its last frame
      activeRef.current = n;
      tRef.current = 0;
      setT(0);
      setActive(n);
    },
    [hold]
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  // one clock for whichever slide is showing; it advances to the next at the end
  useEffect(() => {
    if (reduced) return;
    let visible = true;
    const el = rootRef.current;
    const io = el ? new IntersectionObserver(([e]) => (visible = e.isIntersecting)) : null;
    if (el && io) io.observe(el);
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(64, now - last);
      last = now;
      if (visible) {
        const next = tRef.current + dt;
        if (next >= LENGTHS[activeRef.current]) {
          hold(activeRef.current, LENGTHS[activeRef.current] - 1);
          const n = (activeRef.current + 1) % 3;
          hold(n, POSTER[n]);
          activeRef.current = n;
          tRef.current = 0;
          setT(0);
          setActive(n);
        } else {
          tRef.current = next;
          setT(next);
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      io?.disconnect();
    };
  }, [reduced, hold]);

  // swipe / drag
  const x0 = useRef<number | null>(null);
  const onDown = (e: React.PointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    x0.current = e.clientX;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    if (x0.current === null) return;
    const dx = e.clientX - x0.current;
    if (Math.abs(dx) > 6) setDrag(dx);
  };
  const onUp = () => {
    const dx = drag ?? 0;
    x0.current = null;
    setDrag(null);
    if (dx < -50) go(activeRef.current + 1);
    else if (dx > 50) go(activeRef.current - 1);
  };

  const timeFor = (i: number) => (reduced ? STILL[i] : i === active ? t : held[i]);
  const L = SHELL[locale] ?? SHELL.en;

  return (
    <div ref={rootRef} className={`${s.wrap} ${className ?? ""}`} style={{ "--sp-accent": accent } as CSSProperties}>
      <div
        className={s.tabs}
        role="tablist"
        aria-label="ShortPulse"
        onKeyDown={(e) => {
          if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
          e.preventDefault();
          const n = (active + (e.key === "ArrowRight" ? 1 : 2)) % 3;
          go(n);
          (e.currentTarget.children[n] as HTMLElement | undefined)?.focus();
        }}
      >
        {L.modes.map((label, i) => (
          <button
            key={label}
            type="button"
            role="tab"
            aria-selected={i === active}
            aria-controls={`sp-demo-${i}`}
            tabIndex={i === active ? 0 : -1}
            className={`${s.tab} ${i === active ? s.tabOn : ""}`}
            onClick={() => go(i)}
          >
            <Svg>{ICONS[i]}</Svg>
            <span className={s.label}>{label}</span>
            {i === active && !reduced && (
              <span className={s.bar}>
                <span className={s.barFill} style={{ display: "block", width: `${(t / LENGTHS[i]) * 100}%` }} />
              </span>
            )}
          </button>
        ))}
      </div>

      <div className={s.viewport} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
        {!mounted ? (
          <div className={s.placeholder} aria-hidden />
        ) : (
        <div
          className={`${s.track} ${drag === null ? s.anim : ""}`}
          style={{ transform: `translateX(calc(${-active * 100}% + ${drag ?? 0}px))` }}
        >
          <div id="sp-demo-0" role="tabpanel" aria-hidden={active !== 0} className={`${s.slide} ${active !== 0 ? s.slideOff : ""}`}>
            <ShortPulseDemo assets={assets.generate} locale={locale} accent={accent} time={timeFor(0)} fadeEdges={false} />
          </div>
          <div id="sp-demo-1" role="tabpanel" aria-hidden={active !== 1} className={`${s.slide} ${active !== 1 ? s.slideOff : ""}`}>
            <CaptionDemo assets={assets.caption} locale={locale} accent={accent} time={timeFor(1)} fadeEdges={false} />
          </div>
          <div id="sp-demo-2" role="tabpanel" aria-hidden={active !== 2} className={`${s.slide} ${active !== 2 ? s.slideOff : ""}`}>
            <EditDemo assets={assets.edit} locale={locale} accent={accent} time={timeFor(2)} fadeEdges={false} />
          </div>
        </div>
        )}
      </div>

      <div className={s.arrows}>
        <button type="button" className={s.arrow} aria-label="Previous" onClick={() => go(active - 1)}>
          <Svg>
            <path d="M15 6l-6 6 6 6" />
          </Svg>
        </button>
        <button type="button" className={s.arrow} aria-label="Next" onClick={() => go(active + 1)}>
          <Svg>
            <path d="m9 6 6 6-6 6" />
          </Svg>
        </button>
      </div>
    </div>
  );
}
