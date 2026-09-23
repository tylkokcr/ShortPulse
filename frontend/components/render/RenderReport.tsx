"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getRenderTimings } from "@/lib/api";
import type { RenderTimings } from "@/lib/types";

/**
 * Where the render's time actually went.
 *
 * The pipeline has always measured this per stage and written it next to
 * the output; nothing ever showed it. It is the most honest thing the
 * product can say about itself — not a marketing number, the real wall
 * clock on the machine that did the work — and it happens to be the one
 * thing no closed competitor can show you.
 *
 * Bars are proportional to share of total, so the distribution reads at a
 * glance: on a fast_hybrid render the image stage dwarfs everything else,
 * which is exactly what the pricing is based on.
 */
/** A stage the backend reports but this list doesn't name keeps its own
 *  key, which is still more use than a translated guess. */
const STAGE_KEYS = [
  "script",
  "audio_and_transcription",
  "transcription",
  "visuals",
  "subtitles",
  "ffmpeg_assembly",
] as const;

function seconds(value: number): string {
  if (value >= 60) return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
  if (value >= 10) return `${value.toFixed(0)}s`;
  return `${value.toFixed(1)}s`;
}

export function RenderReport({ projectId }: { projectId: string }) {
  const [timings, setTimings] = useState<RenderTimings | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRenderTimings(projectId)
      .then((data) => {
        if (!cancelled) setTimings(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const t = useTranslations("app.report");
  const stages = timings?.stages_s ? Object.entries(timings.stages_s) : [];
  if (!timings?.total_s || stages.length === 0) return null;

  const slowest = Math.max(...stages.map(([, v]) => v));

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <div className="flex items-baseline justify-between">
        <span className="label">{t("title")}</span>
        <span className="font-mono text-xs text-white/70">
          {t("total", { time: seconds(timings.total_s) })}
        </span>
      </div>

      <div className="flex flex-col gap-1.5">
        {stages.map(([key, value]) => (
          <div key={key} className="flex items-center gap-2.5">
            <span className="w-[86px] shrink-0 truncate text-[11px] text-white/50">
              {(STAGE_KEYS as readonly string[]).includes(key) ? t(`stages.${key}`) : key}
            </span>
            <div className="h-1 flex-1 bg-border">
              <div
                className="h-full bg-accent"
                // Scaled against the slowest stage rather than the total:
                // a stage worth 3% of the render would otherwise be an
                // invisible sliver, and the point is to compare them.
                style={{ width: `${Math.max((value / slowest) * 100, 2)}%` }}
              />
            </div>
            <span className="w-11 shrink-0 text-right font-mono text-[10px] text-white/40">
              {seconds(value)}
            </span>
          </div>
        ))}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 pt-1 font-mono text-[10px]">
        {timings.video_duration_s !== undefined && (
          <Fact label={t("video")} value={`${timings.video_duration_s.toFixed(1)}s`} />
        )}
        {timings.scene_count !== undefined && (
          <Fact label={t("scenes")} value={String(timings.scene_count)} />
        )}
        {timings.word_count !== undefined && (
          <Fact label={t("words")} value={String(timings.word_count)} />
        )}
        {timings.visual_mode && <Fact label={t("mode")} value={timings.visual_mode} />}
        {timings.diffusion_device && <Fact label={t("device")} value={timings.diffusion_device} />}
      </dl>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-white/30">{label}</dt>
      <dd className="truncate text-white/60">{value}</dd>
    </div>
  );
}
