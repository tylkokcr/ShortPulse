"use client";

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  ArrowRight,
  BookOpen,
  Biohazard,
  Check,
  Clapperboard,
  Clock,
  Coins,
  Film,
  Image as ImageIcon,
  Shuffle,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { createProject, getCredits, InsufficientCreditsError, listArtStyles } from "@/lib/api";
import { EPISODE_SHAPE, isSeriesFormat, type SeriesFormat } from "@/lib/series";
import { LANGUAGE_OPTIONS, type ArtStyle, type CreditSummary } from "@/lib/types";
import { useArtStyleText } from "@/lib/artStyleText";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

/**
 * Starting a series: the premise and the few things a series needs that a
 * one-off video does not — its genre, where it happens, the look of people
 * the viewer will see forty times — and an honest summary of what one
 * episode is (two minutes, ~45 shots) and costs.
 */
export default function NewSeriesPage() {
  return (
    <RequireAuth>
      <NewSeries />
    </RequireAuth>
  );
}

const GENRES = ["thriller", "drama", "mystery", "comedy", "romance"] as const;
const STYLE_DEFAULT: Record<SeriesFormat, string> = { story: "vector", outbreak: "toon3d" };
// Photographs of people in a drama read as deepfakes; pixel art cannot act.
const STYLE_HIDDEN = new Set(["photoreal", "pixel"]);
const SERIES_LANGUAGES = new Set(["tr", "en", "pl", "de"]);

type Mode = "ai_video" | "fast_hybrid";
type Length = "short" | "medium";

function NewSeries() {
  const t = useTranslations("app.series");
  const tsc = useTranslations("studio.script");
  const text = useArtStyleText();
  const locale = useLocale();
  const router = useRouter();

  const [format, setFormat] = useState<SeriesFormat>(() => {
    if (typeof window === "undefined") return "story";
    const asked = new URLSearchParams(window.location.search).get("format");
    return isSeriesFormat(asked ?? "") ? (asked as SeriesFormat) : "story";
  });
  const [topic, setTopic] = useState("");
  const [genre, setGenre] = useState<string>("thriller");
  const [setting, setSetting] = useState("");
  const [language, setLanguage] = useState(SERIES_LANGUAGES.has(locale) ? locale : "en");
  const [style, setStyle] = useState(STYLE_DEFAULT[format]);
  const [mode, setMode] = useState<Mode>("ai_video");
  const [length, setLength] = useState<Length>("medium");
  const [styles, setStyles] = useState<ArtStyle[]>([]);
  const [credits, setCredits] = useState<CreditSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listArtStyles().then(setStyles).catch(() => setStyles([]));
    getCredits().then(setCredits).catch(() => setCredits(null));
  }, []);

  function pickFormat(next: SeriesFormat) {
    setFormat(next);
    setStyle(STYLE_DEFAULT[next]);
    const url = new URL(window.location.href);
    url.searchParams.set("format", next);
    window.history.replaceState(null, "", url);
  }

  const price = useMemo(() => {
    const key = `${format === "story" ? "story:" : ""}${mode}:${length}`;
    return credits?.pricing?.[key];
  }, [credits, format, mode, length]);
  const shape = EPISODE_SHAPE[format][length];
  const suggestions =
    format === "story"
      ? (["kitchen", "neighbour", "letter", "basement"] as const)
      : (["city", "school", "island", "metro"] as const);
  const suggestionKey = format === "story" ? "storySuggestions" : "outbreakSuggestions";

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const created = await createProject({
        topic: topic.trim(),
        script_format: format,
        language,
        art_style: style,
        visual_mode: mode,
        video_length: length,
        aspect_ratio: "9:16",
        series_genre: format === "story" ? genre : null,
        series_setting: setting.trim() || null,
      });
      router.push(`/project/${created.config.id}`);
    } catch (err) {
      setError(
        err instanceof InsufficientCreditsError
          ? t("insufficient", { required: err.required, balance: err.balance })
          : err instanceof Error
            ? err.message
            : t("failed")
      );
      setBusy(false);
    }
  }

  return (
    <AppShell section="series">
      <div className="animate-fade-up">
        <h1 className="text-3xl font-semibold tracking-tight">{t("newTitle")}</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-white/50">{t("newIntro")}</p>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-start">
        <div className="flex flex-col gap-4">
          {/* Which kind of series */}
          <div className="grid grid-cols-2 gap-3">
            {(["story", "outbreak"] as const).map((id) => {
              const Icon = id === "story" ? BookOpen : Biohazard;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => pickFormat(id)}
                  aria-pressed={format === id}
                  className={clsx(
                    "flex items-start gap-3 rounded-lg border p-4 text-left transition-colors",
                    format === id
                      ? "border-accent/60 bg-accent/[0.08]"
                      : "border-border bg-surface hover:border-border-strong"
                  )}
                >
                  <Icon size={18} className="mt-0.5 shrink-0 text-accent" />
                  <span>
                    <span className="block text-sm font-semibold">{t(`formats.${id}.name`)}</span>
                    <span className="mt-1 block text-xs leading-relaxed text-white/45">
                      {t(`formats.${id}.short`)}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          <Card className="flex flex-col gap-5 border-border-strong bg-surface-raised">
            {/* Premise */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-white/70">
                {t(`premise.${format}`)}
              </label>
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder={tsc(format === "story" ? "storyPlaceholder" : "outbreakPlaceholder")}
                maxLength={200}
                className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
              />
              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <span className="flex items-center gap-1 text-[11px] text-white/30">
                  <Shuffle size={11} />
                  {tsc("try")}
                </span>
                {suggestions.map((id) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setTopic(tsc(`${suggestionKey}.${id}`))}
                    className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-white/50 transition-colors hover:border-accent/50 hover:bg-accent/10 hover:text-white"
                  >
                    {tsc(`${suggestionKey}.${id}`)}
                  </button>
                ))}
              </div>
            </div>

            {/* Genre (story) */}
            {format === "story" && (
              <div>
                <span className="mb-1.5 block text-sm font-medium text-white/70">{t("genre")}</span>
                <div className="flex flex-wrap gap-2">
                  {GENRES.map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGenre(g)}
                      aria-pressed={genre === g}
                      className={clsx(
                        "rounded-lg border px-3 py-1.5 text-xs transition-colors",
                        genre === g
                          ? "border-accent/60 bg-accent/[0.08] text-white"
                          : "border-border text-white/50 hover:border-border-strong"
                      )}
                    >
                      {t(`genres.${g}`)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Setting + language */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-[minmax(0,1fr)_160px]">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-white/70">
                  {t(`setting.${format}`)}{" "}
                  <span className="text-white/35">{t("optional")}</span>
                </label>
                <input
                  value={setting}
                  onChange={(e) => setSetting(e.target.value)}
                  placeholder={t(`settingPlaceholder.${format}`)}
                  maxLength={80}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-white/70">{t("language")}</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none focus:border-accent"
                >
                  {LANGUAGE_OPTIONS.filter((l) => SERIES_LANGUAGES.has(l.code)).map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Look */}
            <div>
              <span className="mb-1.5 block text-sm font-medium text-white/70">{t("style")}</span>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                {styles
                  .filter((s) => !STYLE_HIDDEN.has(s.id))
                  .map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setStyle(s.id)}
                      aria-pressed={style === s.id}
                      title={text(s).description}
                      className={clsx(
                        "group flex flex-col gap-1.5 rounded-lg border p-1.5 text-left transition-all",
                        style === s.id
                          ? "border-accent bg-accent/10"
                          : "border-border bg-background hover:border-border-strong"
                      )}
                    >
                      <span className="relative block overflow-hidden rounded-md">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={`/art-styles/${s.sample}`}
                          alt=""
                          loading="lazy"
                          className="aspect-[9/16] w-full object-cover"
                        />
                        {style === s.id && (
                          <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent">
                            <Check size={10} className="text-white" />
                          </span>
                        )}
                      </span>
                      <span className="px-0.5 text-[11px] font-medium leading-tight">{text(s).name}</span>
                    </button>
                  ))}
              </div>
            </div>

            {/* Motion */}
            <div>
              <span className="mb-1.5 block text-sm font-medium text-white/70">{t("motion")}</span>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {(["ai_video", "fast_hybrid"] as const).map((m) => {
                  const Icon = m === "ai_video" ? Film : ImageIcon;
                  const cost = credits?.pricing?.[`${format === "story" ? "story:" : ""}${m}:${length}`];
                  return (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMode(m)}
                      aria-pressed={mode === m}
                      className={clsx(
                        "flex items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                        mode === m
                          ? "border-accent/60 bg-accent/[0.08]"
                          : "border-border hover:border-border-strong"
                      )}
                    >
                      <Icon size={16} className="mt-0.5 shrink-0 text-accent" />
                      <span className="flex-1">
                        <span className="flex items-center justify-between gap-2 text-sm font-medium">
                          {t(`motions.${m}.name`)}
                          {cost !== undefined && (
                            <span className="font-mono text-[11px] text-white/45">
                              {t("credits", { count: cost })}
                            </span>
                          )}
                        </span>
                        <span className="mt-0.5 block text-[11px] leading-relaxed text-white/40">
                          {t(`motions.${m}.hint`)}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Length */}
            <div>
              <span className="mb-1.5 block text-sm font-medium text-white/70">{t("length")}</span>
              <div className="flex gap-2">
                {(["short", "medium"] as const).map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => setLength(l)}
                    aria-pressed={length === l}
                    className={clsx(
                      "rounded-lg border px-3 py-1.5 text-xs transition-colors",
                      length === l
                        ? "border-accent/60 bg-accent/[0.08] text-white"
                        : "border-border text-white/50 hover:border-border-strong"
                    )}
                  >
                    {t(`lengths.${l}`, { seconds: EPISODE_SHAPE[format][l].seconds })}
                  </button>
                ))}
              </div>
            </div>
          </Card>

          {error && (
            <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </p>
          )}
        </div>

        {/* What one episode is */}
        <Card className="flex flex-col gap-4 lg:sticky lg:top-6">
          <div className="flex items-center gap-2">
            <Clapperboard size={15} className="text-accent" />
            <h2 className="text-sm font-semibold">{t("summary.title")}</h2>
          </div>
          <dl className="flex flex-col gap-3 text-xs">
            <Row label={t("summary.length")} value={t("summary.seconds", { seconds: shape.seconds })} />
            <Row label={t("summary.shots")} value={shape.shots} />
            <Row label={t("summary.voices")} value={t(`summary.voicesValue.${format}`)} />
            <Row
              label={t("summary.time")}
              value={t("summary.minutes", { minutes: mode === "ai_video" ? "10-15" : "6-10" })}
              icon={Clock}
            />
            <Row
              label={t("summary.cost")}
              value={price !== undefined ? t("credits", { count: price }) : "—"}
              icon={Coins}
            />
          </dl>
          {credits?.enabled && (
            <p className="text-[11px] text-white/35">{t("summary.balance", { balance: credits.balance })}</p>
          )}
          <Button
            variant="gradient"
            onClick={start}
            disabled={busy || topic.trim().length < 3}
            className="w-full"
          >
            {busy ? t("creating") : t("create")}
            {!busy && <ArrowRight size={15} />}
          </Button>
          <p className="text-[11px] leading-relaxed text-white/35">{t("summary.next")}</p>
        </Card>
      </div>
    </AppShell>
  );
}

function Row({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon?: typeof Clock;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="flex items-center gap-1.5 text-white/45">
        {Icon && <Icon size={12} />}
        {label}
      </dt>
      <dd className="text-right font-mono text-white/80">{value}</dd>
    </div>
  );
}
