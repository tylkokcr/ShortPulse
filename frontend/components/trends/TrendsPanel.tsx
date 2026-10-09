"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { ChevronDown, Flame, Loader2, Music2, TrendingDown, TrendingUp } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { getTrendRegions, getTrends } from "@/lib/api";
import type { TrendReport } from "@/lib/types";
import { useShortPulseStore } from "@/lib/store";

const REGION_KEY = "shortpulse.trends.region";
const OPEN_KEY = "shortpulse.trends.open";
const LOCALE_REGION: Record<string, string> = { tr: "TR", pl: "PL", de: "DE", en: "US" };

function remembered(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function remember(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* Private mode: the choice lasts the visit. */
  }
}

const STATUS_STYLE = {
  rising: { icon: TrendingUp, cls: "border-live/40 bg-live/10 text-live" },
  peak: { icon: Flame, cls: "border-accent/40 bg-accent/10 text-accent" },
  fading: { icon: TrendingDown, cls: "border-border text-white/45" },
} as const;

/**
 * One example video. Served through the API (backend routes/trends.py):
 * the CSP keeps images to this origin, and a visitor should not be sending
 * Google a request per card. One that will not load is left out rather
 * than shown as its alt text.
 */
function ExampleThumb({ id, title }: { id: string; title: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <a
      href={`https://www.youtube.com/watch?v=${id}`}
      target="_blank"
      rel="noreferrer"
      title={title}
      className="block w-1/3 overflow-hidden rounded border border-border bg-black/40 hover:border-border-strong"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`/api/trends/thumb/${encodeURIComponent(id)}`}
        alt=""
        loading="lazy"
        onError={() => setFailed(true)}
        className="aspect-video w-full object-cover"
      />
    </a>
  );
}

/**
 * What is catching on in a region, read from YouTube's charts and Apple's
 * most-played songs and grouped into trends by the server (backend
 * services/trends.py). In the topic studio an idea fills the topic; in the
 * beat-edit studio the trends that suit editing come with the songs that
 * are rising.
 */
export function TrendsPanel({ mode }: { mode: "generate" | "edit" }) {
  const t = useTranslations("trends");
  const locale = useLocale();
  const setDraft = useShortPulseStore((s) => s.setDraft);
  const [regions, setRegions] = useState<string[] | null>(null);
  const [region, setRegion] = useState<string>(LOCALE_REGION[locale] ?? "US");
  const [open, setOpen] = useState(true);
  const [report, setReport] = useState<TrendReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const storedRegion = remembered(REGION_KEY);
    const storedOpen = remembered(OPEN_KEY);
    getTrendRegions()
      .then((r) => {
        if (!r.enabled) return;
        setRegions(r.regions);
        if (storedRegion && r.regions.includes(storedRegion)) setRegion(storedRegion);
        if (storedOpen === "0") setOpen(false);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!regions || !open) return;
    let live = true;
    setLoading(true);
    setFailed(false);
    getTrends(region, locale)
      .then((r) => live && setReport(r))
      .catch(() => live && setFailed(true))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [regions, region, locale, open]);

  const names = useMemo(() => {
    try {
      return new Intl.DisplayNames([locale], { type: "region" });
    } catch {
      return null;
    }
  }, [locale]);

  if (!regions) return null;

  const shown = (report?.trends ?? []).filter((trend) =>
    mode === "generate" ? trend.fits !== "edit" : trend.fits !== "generate"
  );

  return (
    <section className="surface-accent rounded-lg border border-border bg-surface/60">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <button
          type="button"
          onClick={() => {
            setOpen((o) => !o);
            remember(OPEN_KEY, open ? "0" : "1");
          }}
          className="flex items-center gap-2 text-sm font-semibold"
          aria-expanded={open}
        >
          <Flame size={15} className="text-accent" />
          {t(mode === "generate" ? "titleGenerate" : "titleEdit")}
          <ChevronDown size={14} className={clsx("text-white/40 transition-transform", open && "rotate-180")} />
        </button>
        <label className="flex items-center gap-2 text-xs text-white/50">
          {t("region")}
          <select
            value={region}
            onChange={(e) => {
              setRegion(e.target.value);
              remember(REGION_KEY, e.target.value);
            }}
            className="rounded-md border border-border bg-black/30 px-2 py-1 text-xs text-white/80"
          >
            {regions.map((code) => (
              <option key={code} value={code}>
                {names?.of(code) ?? code}
              </option>
            ))}
          </select>
        </label>
      </div>

      {open && (
        <div className="flex flex-col gap-4 border-t border-border px-4 py-4">
          {loading ? (
            <p className="flex items-center gap-2 text-xs text-white/45">
              <Loader2 size={13} className="animate-spin" />
              {t("loading")}
            </p>
          ) : failed || !report ? (
            <p className="text-xs text-white/45">{t("failed")}</p>
          ) : (
            <>
              {report.summary && <p className="text-xs leading-relaxed text-white/60">{report.summary}</p>}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {shown.map((trend) => {
                  const status = STATUS_STYLE[trend.status] ?? STATUS_STYLE.rising;
                  return (
                    <article key={trend.name} className="flex flex-col gap-2 rounded-md border border-border bg-black/20 p-3">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className={clsx("flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium", status.cls)}>
                          <status.icon size={10} />
                          {t(`status.${trend.status}`)}
                        </span>
                        <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-white/45">
                          {t(`kind.${trend.kind}`)}
                        </span>
                      </div>
                      <h3 className="text-sm font-semibold">{trend.name}</h3>
                      <p className="text-xs leading-relaxed text-white/55">{trend.why}</p>
                      {trend.examples.length > 0 && (
                        <div className="flex gap-1.5">
                          {trend.examples.map((v) => (
                            <ExampleThumb key={v.id} id={v.id} title={v.title} />
                          ))}
                        </div>
                      )}
                      <ul className="flex flex-col gap-1">
                        {trend.ideas.map((idea) => (
                          <li key={idea} className="flex items-start justify-between gap-2 text-xs text-white/70">
                            <span>• {idea}</span>
                            {mode === "generate" && (
                              <button
                                type="button"
                                onClick={() => setDraft({ topic: idea })}
                                className="shrink-0 rounded border border-border px-2 py-0.5 text-[10px] text-white/60 hover:border-accent hover:text-white"
                              >
                                {t("use")}
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                    </article>
                  );
                })}
              </div>
              {mode === "edit" && report.songs.length > 0 && (
                <div className="flex flex-col gap-2">
                  <h4 className="flex items-center gap-1.5 text-xs font-semibold text-white/70">
                    <Music2 size={12} />
                    {t("songs")}
                  </h4>
                  <ol className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs text-white/60 sm:grid-cols-2">
                    {report.songs.slice(0, 10).map((song, i) => (
                      <li key={`${song.title}-${i}`} className="truncate">
                        <span className="mr-1.5 font-mono text-white/30">{i + 1}</span>
                        {song.url ? (
                          <a href={song.url} target="_blank" rel="noreferrer" className="hover:text-white">
                            {song.title} — {song.artist}
                          </a>
                        ) : (
                          `${song.title} — ${song.artist}`
                        )}
                      </li>
                    ))}
                  </ol>
                  <p className="text-[11px] text-white/35">{t("songsNote")}</p>
                </div>
              )}
              <p className="text-[10px] text-white/30">
                {t("source", {
                  date: new Date(report.fetched_at).toLocaleDateString(locale, { day: "numeric", month: "long" }),
                })}
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}
