"use client";

import { useEffect, useState } from "react";
import { BookOpen, Biohazard, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { getMediaUrl, type MediaUrl } from "@/lib/api";
import type { Series } from "@/lib/series";

/** One series on the hub: its latest episode's poster, its name, how many
 *  episodes, and whether one is still being made. */
export function SeriesCard({ series }: { series: Series }) {
  const t = useTranslations("app.series");
  const first = series.episodes[0];
  const last = series.episodes.at(-1) ?? first;
  const shown = [...series.episodes].reverse().find((e) => e.status === "complete");
  const working = last.status === "rendering" || last.status === "draft";
  const [media, setMedia] = useState<MediaUrl | null>(null);

  useEffect(() => {
    if (!shown) return;
    let live = true;
    getMediaUrl(shown.config.id)
      .then((m) => live && setMedia(m))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [shown]);

  const Icon = series.format === "story" ? BookOpen : Biohazard;
  const title = first.config.topic.split(" · ")[0];

  return (
    <Link href={`/series/${series.id}`} className="group flex flex-col gap-2">
      <div className="relative aspect-[9/16] overflow-hidden rounded-lg border border-border bg-surface transition-colors group-hover:border-border-strong">
        {media?.poster_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={media.poster_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center bg-gradient-to-b from-surface-raised to-background">
            <Icon size={26} className="text-white/20" />
          </div>
        )}
        <span className="absolute left-2 top-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white/80 backdrop-blur">
          {t("episodes", { count: series.episodes.length })}
        </span>
        {working && (
          <span className="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] text-white/80 backdrop-blur">
            <Loader2 size={10} className="animate-spin" />
            {t("working")}
          </span>
        )}
      </div>
      <div className="flex items-start gap-1.5">
        <Icon size={12} className="mt-0.5 shrink-0 text-accent" />
        <span className="line-clamp-2 text-xs font-medium leading-snug">{title}</span>
      </div>
    </Link>
  );
}
