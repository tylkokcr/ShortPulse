"use client";

import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, BookOpen, Biohazard, Loader2, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { deleteProject, listProjects } from "@/lib/api";
import { groupSeries, seriesOf, type Series } from "@/lib/series";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { Card } from "@/components/ui/Card";
import { ProjectCard } from "@/components/library/ProjectCard";
import { NextEpisode } from "@/components/series/NextEpisode";

/**
 * One series: its episodes in order, who is in it, and the next episode.
 *
 * Addressed by any of its episodes' ids — the project page links here from
 * the episode it shows, without knowing which one started the series.
 */
export default function SeriesDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth>
      <SeriesDetail id={id} />
    </RequireAuth>
  );
}

function SeriesDetail({ id }: { id: string }) {
  const t = useTranslations("app.series");
  const [series, setSeries] = useState<Series | null | undefined>(undefined);

  const load = useCallback(() => {
    listProjects()
      .then((projects) => setSeries(seriesOf(groupSeries(projects), id) ?? null))
      .catch(() => setSeries(null));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // An episode still being made is polled, so it appears when it is done.
  const working = series?.episodes.some((e) => e.status === "rendering" || e.status === "draft");
  useEffect(() => {
    if (!working) return;
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, [working, load]);

  const handleDelete = useCallback(
    async (projectId: string) => {
      await deleteProject(projectId).catch(() => {});
      load();
    },
    [load]
  );

  if (series === undefined) {
    return (
      <AppShell section="series">
        <p className="text-sm text-white/40">{t("loading")}</p>
      </AppShell>
    );
  }
  if (series === null) {
    return (
      <AppShell section="series">
        <p className="text-sm text-white/50">{t("notFound")}</p>
        <Link href="/series" className="mt-3 inline-block text-sm text-accent">
          {t("back")}
        </Link>
      </AppShell>
    );
  }

  const first = series.episodes[0];
  const last = series.episodes.at(-1) ?? first;
  const latestScript = [...series.episodes].reverse().find((e) => e.script)?.script;
  const cast = latestScript?.cast?.length
    ? latestScript.cast.map((m) => ({ name: m.name, role: m.role ?? "" }))
    : latestScript?.character
      ? [{ name: latestScript.character.name, role: "" }]
      : [];
  const Icon = series.format === "story" ? BookOpen : Biohazard;
  const brief = [first.config.series_genre && t(`genres.${first.config.series_genre}`), first.config.series_setting]
    .filter(Boolean)
    .join(" · ");

  return (
    <AppShell section="series" wide>
      <Link href="/series" className="inline-flex items-center gap-1.5 text-xs text-white/45 hover:text-white">
        <ArrowLeft size={13} />
        {t("back")}
      </Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 text-xs text-accent">
            <Icon size={14} />
            {t(`formats.${series.format}.name`)}
            {brief && <span className="text-white/40">· {brief}</span>}
          </div>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">{first.config.topic.split(" · ")[0]}</h1>
          <p className="mt-1 text-sm text-white/45">{t("episodes", { count: series.episodes.length })}</p>
        </div>
        <div className="w-full max-w-sm">
          {last.status === "complete" ? (
            <NextEpisode project={last} compact />
          ) : last.status === "rendering" || last.status === "draft" ? (
            <Card className="flex items-center gap-2 p-4 text-sm text-white/60">
              <Loader2 size={15} className="animate-spin text-accent" />
              {t("making", { n: last.script?.episode ?? series.episodes.length })}
            </Card>
          ) : null}
        </div>
      </div>

      {cast.length > 0 && (
        <div className="mt-6">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-white/60">
            <Users size={13} />
            {t("cast")}
          </div>
          <div className="flex flex-wrap gap-2">
            {cast.map((m) => (
              <span key={m.name} className="rounded-full border border-border bg-surface px-3 py-1 text-xs">
                <span className="font-medium">{m.name}</span>
                {m.role && <span className="text-white/40"> · {m.role}</span>}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-5">
        {series.episodes.map((episode, i) => (
          <div key={episode.config.id} className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wide text-white/40">
              {t("episode", { n: episode.script?.episode ?? i + 1 })}
            </span>
            <ProjectCard project={episode} onDelete={handleDelete} />
          </div>
        ))}
      </div>
    </AppShell>
  );
}
