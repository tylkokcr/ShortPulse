"use client";

/* eslint-disable @next/next/no-img-element */
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import s from "./ShortPulseDemo.module.css";

/** Shared pieces of the ShortPulse demos: easing, icons, cursor, clock, the phone. */

export const W = 1120;
export const H = 700;
export type Locale = "tr" | "en" | "pl" | "de";
export type Path = [number, number, number][];

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

export const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const prog = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
export const inOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
export const out = (x: number) => 1 - Math.pow(1 - x, 3);
export const back = (x: number) => {
  const c1 = 1.7;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
};
export const lerp = (a: number, b: number, x: number) => a + (b - a) * x;
export const typed = (str: string, t: number, a: number, b: number) => str.slice(0, Math.round(str.length * prog(t, a, b)));
export const showHide = (t: number, a: number, b: number, fade = 250) => Math.min(prog(t, a, a + fade), 1 - prog(t, b - fade, b));

export function cursorAt(path: Path, t: number) {
  if (t <= path[0][0]) return { x: path[0][1], y: path[0][2] };
  for (let i = 0; i < path.length - 1; i++) {
    const [t0, x0, y0] = path[i];
    const [t1, x1, y1] = path[i + 1];
    if (t >= t0 && t < t1) {
      const e = inOut(prog(t, t0, t1));
      return { x: lerp(x0, x1, e), y: lerp(y0, y1, e) };
    }
  }
  const l = path[path.length - 1];
  return { x: l[1], y: l[2] };
}

/* ------------------------------------------------------------------ */
/* Icons                                                               */
/* ------------------------------------------------------------------ */

export const PATHS: Record<string, ReactNode> = {
  pulse: <path d="M2 12h4l2.5-6 4 13 3-9 1.5 2H22" />,
  film: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M7 3v18M17 3v18M3 7.5h4M3 12h18M3 16.5h4M17 7.5h4M17 16.5h4" />
    </>
  ),
  zap: <path d="M13 2 3 14h9l-1 8 10-12h-9z" />,
  volume: <path d="M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14" />,
  wand: <path d="m15 4 1.5 1.5M19.5 8.5 21 10M14 8l-11 11 2 2 11-11zM18 3v2M22 7h-2M20 2l-1 1" />,
  library: (
    <>
      <path d="M4 4v16M8 4v16" />
      <path d="m12 4.5 4 15.5 4-1-4-15.5z" />
    </>
  ),
  folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  share: (
    <>
      <circle cx="18" cy="5" r="2.5" />
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="19" r="2.5" />
      <path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4" />
    </>
  ),
  coins: (
    <>
      <circle cx="9" cy="9" r="6" />
      <path d="M15.5 9.5a6 6 0 1 1-6 6" />
    </>
  ),
  flame: <path d="M12 3c1 4 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-3.5 2-5 1 1 1.5 2 1.5 3 1.5-1.5 2-4.5 1.5-8Z" />,
  trend: <path d="M3 17 9 11l4 4 8-8M15 7h6v6" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />,
  scissors: (
    <>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12" />
    </>
  ),
  doc: <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4" />,
  grid: <path d="M4 9h16M4 15h16M9 4v16M15 4v16" />,
  palette: (
    <>
      <circle cx="13.5" cy="6.5" r="1" fill="currentColor" />
      <circle cx="17.5" cy="10.5" r="1" fill="currentColor" />
      <circle cx="8.5" cy="7.5" r="1" fill="currentColor" />
      <path d="M12 2a10 10 0 0 0 0 20 2 2 0 0 0 2-2c0-1-1-1.6-1-2.6a1.8 1.8 0 0 1 1.8-1.8H17a5 5 0 0 0 5-5c0-4.8-4.5-8.6-10-8.6Z" />
    </>
  ),
  music: (
    <>
      <path d="M9 18V5l12-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="16" r="3" />
    </>
  ),
  chevron: <path d="m9 6 6 6-6 6" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  back: <path d="M19 12H5M11 6l-6 6 6 6" />,
  check: <path d="M20 6 9 17l-5-5" />,
  download: <path d="M12 15V3M7 10l5 5 5-5M5 21h14" />,
  send: <path d="M22 2 11 13M22 2l-7 20-4-9-9-4z" />,
  image: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 17v5" />
    </>
  ),
  type: <path d="M4 7V4h16v3M9 20h6M12 4v16" />,
  thumb: <path d="M7 10v11M15 5.9 14 10h5.8a2 2 0 0 1 2 2.3l-1.4 7A2 2 0 0 1 18.5 21H7V10l4-8a3 3 0 0 1 4 3.9Z" />,
  refresh: <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.3L3 16M3 21v-5h5" />,
  play: <path d="M7 4.5v15a1 1 0 0 0 1.5.9l12-7.5a1 1 0 0 0 0-1.7l-12-7.5A1 1 0 0 0 7 4.5Z" fill="currentColor" />,
  plus: <path d="M12 5v14M5 12h14" />,
  yt: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="4" />
      <path d="m10 9 5 3-5 3z" fill="currentColor" />
    </>
  ),
  tt: <path d="M14 3v11.5a3.5 3.5 0 1 1-3.5-3.5M14 3c.5 2.5 2.5 4.5 5 4.5" />,
};

export function Icon({ name, size = 15, style }: { name: keyof typeof PATHS; size?: number; style?: CSSProperties }) {
  return (
    <svg className={s.icon} style={{ width: size, height: size, ...style }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {PATHS[name]}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* Clock + scale                                                       */
/* ------------------------------------------------------------------ */

/** Own clock when `frozen` is undefined; pauses off-screen; loops at `length`. */
export function useDemoClock(
  frozen: number | undefined,
  speed: number,
  rootRef: React.RefObject<HTMLDivElement | null>,
  length: number,
  reducedFrame: number,
) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (frozen !== undefined) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setT(reducedFrame);
      return;
    }
    let visible = true;
    const el = rootRef.current;
    const io = el ? new IntersectionObserver(([e]) => (visible = e.isIntersecting)) : null;
    if (el && io) io.observe(el);
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    const loop = (now: number) => {
      const dt = Math.min(64, now - last);
      last = now;
      if (visible) {
        acc = (acc + dt * speed) % length;
        setT(acc);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      io?.disconnect();
    };
  }, [frozen, speed, rootRef, length, reducedFrame]);
  return frozen ?? t;
}

export function useStageScale(rootRef: React.RefObject<HTMLDivElement | null>) {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setScale(e.contentRect.width / W));
    ro.observe(el);
    return () => ro.disconnect();
  }, [rootRef]);
  return scale;
}

/* ------------------------------------------------------------------ */
/* Cursor                                                              */
/* ------------------------------------------------------------------ */

export function Cursor({ t, path, clicks, pressed = [] }: { t: number; path: Path; clicks: number[]; pressed?: [number, number][] }) {
  const { x, y } = cursorAt(path, t);
  const last = [...clicks].reverse().find((c) => c <= t);
  const since = last === undefined ? 9999 : t - last;
  const press = since < 160 ? 1 - Math.abs(since - 80) / 80 : 0;
  const held = pressed.some(([a, b]) => t >= a && t <= b);
  const ripple = since < 450 ? since / 450 : -1;
  return (
    <>
      {ripple >= 0 && (
        <div className={s.ripple} style={{ left: x - 4 - ripple * 16, top: y - 4 - ripple * 16, width: 8 + ripple * 32, height: 8 + ripple * 32, opacity: 0.9 * (1 - ripple) }} />
      )}
      <svg className={s.cursor} viewBox="0 0 24 24" style={{ transform: `translate(${x - 3}px, ${y - 2}px) scale(${held ? 0.88 : 1 - 0.14 * press})`, transformOrigin: "3px 2px" }} aria-hidden>
        <path d="M4 2.5 19.5 11l-6.9 1.9-3.2 6.8z" fill="#fff" stroke="#0a0b0e" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Phone — the vertical short with kinetic captions                     */
/* ------------------------------------------------------------------ */

export type CapStyle = 0 | 1 | 2; // classic, highlight, boxed

export function Phone({
  x,
  y,
  w,
  h,
  src,
  kb = 0,
  reveal = 1,
  words,
  hi,
  wordIn,
  style,
  progress,
  wave,
  phase = 0,
  radius,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  src?: string;
  kb?: number;
  reveal?: number;
  words?: string[];
  hi?: number;
  wordIn?: (i: number) => number;
  style: CapStyle;
  progress?: number;
  wave?: number;
  phase?: number;
  radius?: number;
}) {
  const fs = w * 0.105;
  return (
    <div className={s.phone} style={{ left: x, top: y, width: w, height: h, borderRadius: radius }}>
      {src && reveal > 0 && (
        <img
          className={s.phoneImg}
          src={src}
          alt=""
          draggable={false}
          style={{ opacity: reveal, filter: `blur(${(1 - reveal) * 14}px)`, transform: `scale(${1.04 + kb * 0.08}) translateY(${-kb * 6}px)` }}
        />
      )}
      {words && (
        <div className={s.capWrap} style={{ fontSize: fs }}>
          {words.map((wd, i) => {
            const k = wordIn ? wordIn(i) : 1;
            if (k <= 0) return null;
            const isHi = i === hi && style !== 0;
            return (
              <span
                key={i}
                className={`${s.capWord} ${isHi && style === 1 ? s.capHi : ""} ${isHi && style === 2 ? s.capBox : ""}`}
                style={{ transform: `scale(${0.6 + 0.4 * back(k)})`, opacity: clamp(k * 2) }}
              >
                {wd}
              </span>
            );
          })}
        </div>
      )}
      {wave !== undefined && wave > 0 && (
        <div className={s.wave} style={{ opacity: wave }}>
          {Array.from({ length: 28 }, (_, i) => (
            <i key={i} style={{ height: `${18 + 82 * Math.abs(Math.sin(i * 0.9 + phase / 110) * Math.sin(i * 0.37 + phase / 290 + 1))}%` }} />
          ))}
        </div>
      )}
      {progress !== undefined && <div className={s.progress} style={{ width: `${progress * 100}%` }} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* App shell: rail + header + backdrop                                 */
/* ------------------------------------------------------------------ */

export const SHELL = {
  tr: {
    nav: ["Stüdyo", "Kütüphane", "Dosyalarım", "Bağlantılar", "Krediler"],
    headers: ["STÜDYO", "PROJE", "KÜTÜPHANE"],
    credits: "kredi",
    left: "kaldı",
    modes: ["Konudan üret", "Videomu altyazıla veya seslendir", "Kliplerimle edit"],
  },
  en: {
    nav: ["Studio", "Library", "My files", "Connections", "Credits"],
    headers: ["STUDIO", "PROJECT", "LIBRARY"],
    credits: "credits",
    left: "remaining",
    modes: ["Generate from a topic", "Caption or dub my video", "Edit my clips"],
  },
  pl: {
    nav: ["Studio", "Biblioteka", "Moje pliki", "Połączenia", "Kredyty"],
    headers: ["STUDIO", "PROJEKT", "BIBLIOTEKA"],
    credits: "kredytów",
    left: "pozostało",
    modes: ["Wygeneruj z tematu", "Dodaj napisy lub dubbing", "Montaż z moich klipów"],
  },
  de: {
    nav: ["Studio", "Bibliothek", "Meine Dateien", "Verbindungen", "Credits"],
    headers: ["STUDIO", "PROJEKT", "BIBLIOTHEK"],
    credits: "Credits",
    left: "übrig",
    modes: ["Aus einem Thema erzeugen", "Mein Video untertiteln oder synchronisieren", "Meine Clips schneiden"],
  },
};

export function Shell({ locale, credits, pillY, activeNav, header }: { locale: Locale; credits: number; pillY: number; activeNav: number; header: string }) {
  const L = SHELL[locale];
  return (
    <>
      <div className={s.rail}>
        <div className={s.brand}>
          <span className={s.brandMark}>
            <Icon name="pulse" size={16} style={{ strokeWidth: 2.2 }} />
          </span>
          ShortPulse
        </div>
        <div className={s.navPill} style={{ top: pillY }} />
        {(["wand", "library", "folder", "share", "coins"] as const).map((ic, i) => (
          <div key={ic} className={`${s.nav} ${activeNav === i ? s.navOn : ""}`} style={{ top: 70 + i * 36 }}>
            <Icon name={ic} size={15} /> {L.nav[i]}
          </div>
        ))}
        <div className={s.railFoot}>
          {L.nav[4]}
          <b>
            {credits} {L.credits}
          </b>
        </div>
      </div>
      <div className={s.header}>
        <div className={`${s.headerLabel} ${s.mono}`}>{header}</div>
        <div className={s.headerCredits}>
          <Icon name="coins" size={13} /> {credits}
        </div>
      </div>
    </>
  );
}

/** The Studio hero: title with one accent word, a subline, and the three mode tabs. */
export function StudioHead({ locale, title, sub, mode }: { locale: Locale; title: [string, string, string]; sub: string; mode: 0 | 1 | 2 }) {
  const L = SHELL[locale];
  return (
    <>
      <div className={s.h1} style={{ left: 214, top: 64 }}>
        {title[0]}
        <span className={s.accent}>{title[1]}</span>
        {title[2]}
      </div>
      <div className={s.sub} style={{ left: 214, top: 108 }}>
        {sub}
      </div>
      <div className={s.abs} style={{ left: 214, top: 136, display: "flex", gap: 6 }}>
        {(["wand", "upload", "scissors"] as const).map((ic, i) => (
          <span key={ic} className={`${s.chip} ${i === mode ? s.chipOn : ""}`} style={{ height: 30 }}>
            <Icon name={ic} size={13} /> {L.modes[i]}
          </span>
        ))}
      </div>
    </>
  );
}
