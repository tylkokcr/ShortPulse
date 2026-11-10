"use client";

import { useState } from "react";
import { ArrowRight, Clapperboard } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { createProject, InsufficientCreditsError } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

/**
 * The next episode of a series, one click from the last.
 *
 * Everything the series is — the format, the language, the look, the
 * brief — is carried over from this episode, and the server reads its
 * recap, cast, places and sheets from `continues_from`. Nothing to fill
 * in, which is the point: a cliffhanger wants the next episode now.
 */
export function NextEpisode({ project, compact = false }: { project: Project; compact?: boolean }) {
  const t = useTranslations("app.project");
  const ts = useTranslations("app.series");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = (project.script?.episode ?? 1) + 1;
  const name = project.script?.character?.name ?? project.script?.cast?.[0]?.name ?? "";

  async function start() {
    setBusy(true);
    setError(null);
    const c = project.config;
    try {
      const created = await createProject({
        topic: `${c.topic.split(" · ")[0]} · ${t("nextEpisode.topic", { n: next })}`.slice(0, 200),
        continues_from: c.id,
        script_format: c.script_format,
        language: c.language,
        visual_mode: c.visual_mode,
        art_style: c.art_style,
        aspect_ratio: c.aspect_ratio,
        video_length: c.video_length,
        voice: c.voice,
        music: c.music,
        subtitles: c.subtitles,
        info_graphics: c.info_graphics,
        series_genre: c.series_genre,
        series_setting: c.series_setting,
      });
      router.push(`/project/${created.config.id}`);
    } catch (err) {
      setError(
        err instanceof InsufficientCreditsError
          ? t("nextEpisode.insufficient", { required: err.required, balance: err.balance })
          : t("nextEpisode.failed")
      );
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <Clapperboard size={15} className="text-accent" />
        <h2 className="text-sm font-semibold">{t("nextEpisode.title", { n: project.script?.episode ?? 1 })}</h2>
      </div>
      {!compact && <p className="text-xs leading-relaxed text-white/50">{t("nextEpisode.body", { name })}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={start} disabled={busy} className="w-fit">
          {busy ? t("nextEpisode.creating") : t("nextEpisode.cta", { n: next })}
          {!busy && <ArrowRight size={14} />}
        </Button>
        {!compact && (
          <Link href={`/series/${project.config.id}`} className="text-xs text-white/50 hover:text-white">
            {ts("viewSeries")}
          </Link>
        )}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </Card>
  );
}
