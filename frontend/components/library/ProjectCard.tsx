"use client";

import { useEffect, useState } from "react";
import { Loader2, Play, Scissors, Trash2, TriangleAlert, Upload, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import clsx from "clsx";
import { Link } from "@/i18n/navigation";
import { getMediaUrl } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

/**
 * One project in the library grid.
 *
 * The thumbnail is fetched per card rather than served from a static path,
 * because the poster sits behind the same signed short-lived URL as the
 * video — a project's frames are no more public than the project. Cards
 * for a render that hasn't finished have nothing to show yet and say so,
 * rather than holding an empty box.
 */
export function ProjectCard({
  project,
  onDelete,
}: {
  project: Project;
  onDelete: (id: string) => void;
}) {
  const t = useTranslations("app.library");
  const [poster, setPoster] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const id = project.config.id;
  const complete = project.status === "complete";
  // An extraction has no video of its own. Without this the card offered
  // a play triangle and called it "Captioned", both of which describe the
  // clips rather than the thing being clicked.
  const clipCount = project.clip_project_ids?.length ?? 0;

  useEffect(() => {
    // An extraction has no media to ask for; the request would 404 and
    // the catch below would swallow it, which is a round trip to learn
    // something already known.
    if (!complete || clipCount > 0) return;
    let cancelled = false;
    getMediaUrl(id)
      .then((media) => {
        if (!cancelled) setPoster(media.poster_url);
      })
      // Projects rendered before posters existed have none. The gradient
      // placeholder below is the whole fallback.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id, complete, clipCount]);

  const isUpload = project.config.source === "upload";

  return (
    <div className="group relative flex flex-col gap-2.5">
      <Link
        href={`/project/${id}`}
        className="relative block aspect-[9/16] overflow-hidden rounded-md border border-border bg-surface transition-all duration-300 hover:border-border-strong hover:shadow-xl hover:shadow-black/40"
      >
        {poster ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={poster}
            alt=""
            className="animate-fade-in h-full w-full object-cover"
            onError={() => setPoster(null)}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-surface-raised to-background">
            {project.status === "rendering" ? (
              <Loader2 size={20} className="animate-spin text-accent" />
            ) : project.status === "failed" ? (
              <TriangleAlert size={20} className="text-red-400/70" />
            ) : clipCount ? (
              <Scissors size={20} className="text-white/20" />
            ) : (
              <Play size={20} className="text-white/20" />
            )}
          </div>
        )}

        <Badge
          tone="neutral"
          className="absolute left-2 top-2 flex items-center gap-1 border-white/10 bg-black/60 px-2 py-0.5 text-[10px] text-white/70 backdrop-blur"
        >
          {clipCount ? (
            <Scissors size={9} />
          ) : isUpload ? (
            <Upload size={9} />
          ) : (
            <Wand2 size={9} />
          )}
          {clipCount
            ? t("badge.clips", { count: clipCount })
            : isUpload
              ? t("badge.captioned")
              : t("badge.generated")}
        </Badge>

        {project.status !== "complete" && (
          <Badge
            tone="neutral"
            className={clsx(
              "absolute right-2 top-2 px-2 py-0.5 text-[10px] backdrop-blur",
              project.status === "failed"
                ? "border-red-500/30 bg-red-500/15 text-red-300"
                : "border-white/10 bg-black/60 text-white/70"
            )}
          >
            {t(`status.${project.status}`)}
          </Badge>
        )}
      </Link>

      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium">{project.config.topic}</p>
          <p className="mt-0.5 font-mono text-[10px] text-white/35">
            {project.config.language.toUpperCase()} · {project.config.aspect_ratio}
            {project.credits_cost > 0 && ` · ${t("credits", { count: project.credits_cost })}`}
          </p>
        </div>

        <button
          type="button"
          onClick={() => (confirming ? onDelete(id) : setConfirming(true))}
          onBlur={() => setConfirming(false)}
          aria-label={confirming ? t("confirmDelete") : t("delete")}
          className={clsx(
            // Revealed on hover on a pointer device, always visible on a
            // touch one — there is no hover on a phone, so hiding it there
            // makes deleting a project impossible rather than tidy. The
            // padding is the tap target, not decoration.
            "shrink-0 rounded-md p-2.5 transition-all duration-200",
            confirming
              ? "bg-red-500/20 text-red-400"
              : "text-white/40 hover:text-red-400 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
          )}
        >
          <Trash2 size={13} />
        </button>
      </div>

      {confirming && (
        <p className="text-[10px] leading-tight text-red-400/80">
          {t("deleteWarning")}
        </p>
      )}
    </div>
  );
}
