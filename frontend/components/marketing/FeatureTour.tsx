"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  Facebook,
  Hammer,
  Instagram,
  Languages,
  PenLine,
  Scissors,
  Send,
  Wand2,
  Youtube,
} from "lucide-react";
import { useTranslations } from "next-intl";

/**
 * The whole app in one frame: what it does, one tab per job.
 *
 * This replaced two screenshots side by side, which showed one tab of the
 * studio and the library and left everything else — generating from a
 * topic, dubbing, the editor, posting — to be guessed at. A visitor who
 * did not build this could not have told that it posts for you.
 *
 * Four of the five screens are captures of the running app at the same
 * size and crop, so switching tabs changes what is on the screen and not
 * the zoom. The fifth, posting, is drawn: the connections page needs a
 * signed-in account with a real channel behind it, and a capture of that
 * would be somebody's channel. The drawing uses the same parts as the
 * page — the row, the switch, the in-progress label — and says only what
 * the page says.
 *
 * It steps through the tabs on its own while it is on screen, and stops
 * for good the moment someone picks one: after that, moving on by itself
 * would be taking the screen away from a person who is reading it.
 */
const TABS = [
  { key: "create", icon: Wand2, src: "/tour/create.jpg" },
  { key: "dub", icon: Languages, src: "/tour/dub.jpg" },
  { key: "clips", icon: Scissors, src: "/tour/library.jpg" },
  { key: "edit", icon: PenLine, src: "/tour/edit.jpg" },
  { key: "publish", icon: Send, src: null },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** Every capture was cut to this, so the frame never changes shape. */
const SHOT = { width: 1280, height: 711 };
const STEP_MS = 6000;

export function FeatureTour() {
  const t = useTranslations("tour");
  const [active, setActive] = useState<TabKey>("create");
  const [auto, setAuto] = useState(true);
  const [visible, setVisible] = useState(false);
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const node = root.current;
    if (!node) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      threshold: 0.4,
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!auto || !visible) return;
    const timer = window.setTimeout(() => {
      const i = TABS.findIndex((tab) => tab.key === active);
      setActive(TABS[(i + 1) % TABS.length].key);
    }, STEP_MS);
    return () => window.clearTimeout(timer);
  }, [auto, visible, active]);

  function pick(key: TabKey) {
    setAuto(false);
    setActive(key);
  }

  return (
    <section ref={root} className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">
          {t("eyebrow")}
        </span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
        <p className="max-w-xl text-sm text-white/50">{t("sub")}</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr] lg:items-start">
        {/* The jobs. A row that scrolls on a phone, a list beside the
            screen on a wide one — the description only for the one that
            is open, so the list stays a list. */}
        <div
          role="tablist"
          aria-label={t("title")}
          className="-mx-6 flex gap-2 overflow-x-auto px-6 pb-1 [scrollbar-width:none] lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0"
        >
          {TABS.map((tab) => {
            const selected = tab.key === active;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls="tour-screen"
                onClick={() => pick(tab.key)}
                className={clsx(
                  "relative flex shrink-0 flex-col gap-1 overflow-hidden rounded-lg border px-4 py-3 text-left transition-colors",
                  selected
                    ? "border-accent/50 bg-accent/[0.08]"
                    : "border-border bg-surface hover:border-border-strong"
                )}
              >
                <span className="flex items-center gap-2.5">
                  <tab.icon
                    size={16}
                    className={clsx("shrink-0", selected ? "text-accent" : "text-white/40")}
                  />
                  <span
                    className={clsx(
                      "whitespace-nowrap text-sm font-medium",
                      selected ? "text-white" : "text-white/60"
                    )}
                  >
                    {t(`${tab.key}.title`)}
                  </span>
                  {tab.key === "publish" || tab.key === "clips" || tab.key === "dub" ? (
                    <span className="rounded border border-accent/40 px-1 font-mono text-[9px] uppercase tracking-wider text-accent">
                      {t("new")}
                    </span>
                  ) : null}
                </span>
                <span
                  className={clsx(
                    "hidden text-xs leading-relaxed text-white/50 lg:block",
                    !selected && "lg:hidden"
                  )}
                >
                  {t(`${tab.key}.detail`)}
                </span>
                {/* How long until the next one — only while it is still
                    moving on by itself. Keyed so it restarts per tab. */}
                {selected && auto && visible && (
                  <span
                    key={active}
                    className="tour-progress absolute inset-x-0 bottom-0 h-0.5 origin-left bg-accent/60"
                    style={{ animationDuration: `${STEP_MS}ms` }}
                  />
                )}
              </button>
            );
          })}
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          <div
            id="tour-screen"
            role="tabpanel"
            className="relative w-full overflow-hidden rounded-xl border border-border bg-[#0a0a0a] shadow-2xl shadow-black/40"
            style={{ aspectRatio: `${SHOT.width} / ${SHOT.height}` }}
          >
            {/* All mounted, one shown: switching is a fade rather than a
                load, and the four images are ~300KB together. */}
            {TABS.map((tab) =>
              tab.src ? (
                // Captured at this size for this slot — see ClipShowcase
                // on why these skip the image optimiser.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={tab.key}
                  src={tab.src}
                  alt={t(`${tab.key}.alt`)}
                  width={SHOT.width}
                  height={SHOT.height}
                  loading="lazy"
                  className={clsx(
                    "absolute inset-0 h-full w-full object-cover transition-opacity duration-500",
                    tab.key === active ? "opacity-100" : "opacity-0"
                  )}
                />
              ) : (
                <div
                  key={tab.key}
                  aria-hidden={tab.key !== active}
                  className={clsx(
                    "absolute inset-0 transition-opacity duration-500",
                    tab.key === active ? "opacity-100" : "pointer-events-none opacity-0"
                  )}
                >
                  <PublishScreen />
                </div>
              )
            )}
          </div>
          {/* On a phone the list is a row of names, so the sentence that
              says what the tab does sits under the screen instead. */}
          <p className="text-xs leading-relaxed text-white/50 lg:hidden">
            {t(`${active}.detail`)}
          </p>
        </div>
      </div>
    </section>
  );
}

/**
 * The connections page, drawn. Proportions follow the real one — a row
 * per platform, the switch under the connected account — scaled to sit
 * in the same frame as the captures.
 */
function PublishScreen() {
  const screen = useTranslations("tour.publishScreen");
  return (
    <div className="flex h-full w-full">
      {/* The app's sidebar, so this reads as the same app as the rest. */}
      <div className="hidden w-[14%] shrink-0 border-r border-white/[0.06] sm:block" />
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-[3%] px-[8%] py-[5%]">
        <div>
          <span className="font-mono text-[9px] uppercase tracking-widest text-accent sm:text-[10px]">
            {screen("eyebrow")}
          </span>
          <p className="mt-1 text-base font-semibold tracking-tight sm:text-2xl">{screen("title")}</p>
        </div>

        <div className="flex flex-col gap-2 sm:gap-3">
          <div className="rounded-lg border border-border bg-surface p-2.5 sm:p-4">
            <div className="flex items-center gap-2.5">
              <Youtube size={16} className="shrink-0 text-accent" />
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-medium sm:text-sm">YouTube</span>
                <span className="block truncate text-[10px] text-white/40 sm:text-xs">
                  {screen("channel")}
                </span>
              </span>
            </div>
            <div className="mt-2.5 flex items-start gap-2.5 border-t border-border pt-2.5 sm:mt-4 sm:gap-3 sm:pt-4">
              <span className="relative mt-0.5 h-4 w-7 shrink-0 rounded-full bg-accent sm:h-5 sm:w-9">
                <span className="absolute left-0.5 top-0.5 h-3 w-3 translate-x-3 rounded-full bg-white sm:h-4 sm:w-4 sm:translate-x-4" />
              </span>
              <span>
                <span className="block text-[11px] font-medium text-white/80 sm:text-sm">
                  {screen("autoTitle")}
                </span>
                <span className="mt-0.5 block text-[10px] leading-relaxed text-white/40 sm:text-xs">
                  {screen("autoOn")}
                </span>
              </span>
            </div>
          </div>

          {[
            { name: "Instagram", icon: Instagram },
            { name: "Facebook", icon: Facebook },
          ].map((platform) => (
            <div
              key={platform.name}
              className="flex items-center gap-2.5 rounded-lg border border-border bg-surface p-2.5 opacity-60 sm:p-4"
            >
              <platform.icon size={16} className="shrink-0 text-white/30" />
              <span className="flex-1 text-xs font-medium text-white/70 sm:text-sm">
                {platform.name}
              </span>
              <span className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-white/45 sm:text-xs">
                <Hammer size={11} />
                {screen("soon")}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
