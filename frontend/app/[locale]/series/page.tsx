"use client";

import { useEffect, useState } from "react";
import { ArrowRight, BookOpen, Clapperboard, HelpCircle, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { listProjects } from "@/lib/api";
import { groupSeries, type FormatChoice, type Series } from "@/lib/series";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { SeriesCard } from "@/components/series/SeriesCard";

/**
 * Formats: the kinds of video with rules and a look of their own — a one-off
 * What if?, and story series made in episodes, whose cast and places carry
 * over.
 *
 * Their own place rather than more chips in the studio's format row:
 * a series is something you come back to — episode two tomorrow — and
 * what you choose when starting one (a genre, a city, a look for people
 * you will see forty times) is not what a one-off video asks.
 */
export default function SeriesPage() {
  return (
    <RequireAuth>
      <SeriesHub />
    </RequireAuth>
  );
}

// An outbreak is a story genre now, chosen in the story form.
const FORMATS: { id: FormatChoice; icon: typeof BookOpen }[] = [
  { id: "what_if", icon: HelpCircle },
  { id: "story", icon: BookOpen },
];
const WHAT_IF_SAMPLES = new Set(["tr", "en", "pl", "de"]);

function SeriesHub() {
  const t = useTranslations("app.series");
  const locale = useLocale();
  const sample = (id: FormatChoice) =>
    id === "what_if"
      ? `/showcase/whatif-${WHAT_IF_SAMPLES.has(locale) ? locale : "en"}`
      : `/series/${id}`;
  const [series, setSeries] = useState<Series[] | null>(null);

  useEffect(() => {
    listProjects()
      .then((projects) => setSeries(groupSeries(projects)))
      .catch(() => setSeries([]));
  }, []);

  return (
    <AppShell section="series" wide>
      <div className="animate-fade-up">
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/50">{t("intro")}</p>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-5 md:grid-cols-2">
        {FORMATS.map((format, i) => (
          <Reveal key={format.id} delay={i * 80}>
            <Card className="flex h-full flex-col gap-4 overflow-hidden p-0 sm:flex-row">
              <video
                src={`${sample(format.id)}.mp4`}
                poster={`${sample(format.id)}.jpg`}
                muted
                loop
                autoPlay
                playsInline
                preload="metadata"
                className="aspect-[9/16] w-full bg-black object-cover sm:w-44"
              />
              <div className="flex flex-1 flex-col gap-3 p-5 sm:pl-1">
                <div className="flex items-center gap-2">
                  <format.icon size={16} className="text-accent" />
                  <h2 className="text-lg font-semibold">{t(`formats.${format.id}.name`)}</h2>
                </div>
                <p className="text-sm leading-relaxed text-white/55">{t(`formats.${format.id}.body`)}</p>
                <ul className="flex flex-col gap-1.5 text-xs text-white/45">
                  {(["a", "b", "c"] as const).map((k) => (
                    <li key={k} className="flex gap-2">
                      <span className="text-accent">•</span>
                      {t(`formats.${format.id}.points.${k}`)}
                    </li>
                  ))}
                </ul>
                <Link href={`/series/new?format=${format.id}`} className="mt-auto w-fit">
                  <Button variant="gradient">
                    {t("start")}
                    <ArrowRight size={15} />
                  </Button>
                </Link>
              </div>
            </Card>
          </Reveal>
        ))}
      </div>

      <div className="mt-12 flex items-center gap-2">
        <Clapperboard size={16} className="text-accent" />
        <h2 className="text-base font-semibold">{t("mine")}</h2>
      </div>
      {series === null ? (
        <p className="mt-4 text-sm text-white/40">{t("loading")}</p>
      ) : series.length === 0 ? (
        <div className="mt-6 flex flex-col items-start gap-3 rounded-lg border border-dashed border-border p-6">
          <p className="text-sm text-white/50">{t("none")}</p>
          <Link href="/series/new?format=story">
            <Button variant="secondary">
              <Plus size={15} />
              {t("startFirst")}
            </Button>
          </Link>
        </div>
      ) : (
        <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-5">
          {series.map((s, i) => (
            <Reveal key={s.id} delay={(i % 5) * 55}>
              <SeriesCard series={s} />
            </Reveal>
          ))}
        </div>
      )}
    </AppShell>
  );
}
