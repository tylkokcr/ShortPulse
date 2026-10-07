"use client";

import { useEffect, useState } from "react";
import { Film, Gauge, Music, Scissors, Timer, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { getRenderTimings } from "@/lib/api";
import type { BeatEditSpec, RenderTimings } from "@/lib/types";
import { Card } from "@/components/ui/Card";

function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * How a beat edit was made: style, length, song and where in it, clips,
 * and what the render found — so two tries can be compared without
 * remembering which was which. What was asked comes from the project;
 * what was used (the start when left to the server, the tempo, the
 * number of cuts) from the render report.
 */
export function BeatEditDetails({ projectId, spec }: { projectId: string; spec: BeatEditSpec }) {
  const t = useTranslations("app.beatDetails");
  const tb = useTranslations("studio.beat");
  const [timings, setTimings] = useState<RenderTimings | null>(null);

  useEffect(() => {
    let live = true;
    getRenderTimings(projectId)
      .then((data) => live && setTimings(data))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [projectId]);

  const start = timings?.music_start_s ?? spec.music_start_s ?? null;
  const song = spec.music_uploaded ? t("ownSong") : (spec.music_track_id ?? "—");
  const rows: { icon: typeof Wand2; label: string; value: string }[] = [
    { icon: Wand2, label: t("style"), value: tb(`styles.${spec.style}.name`) },
    { icon: Timer, label: t("length"), value: `${Math.round(spec.duration_s)}s` },
    { icon: Music, label: t("song"), value: song },
    {
      icon: Music,
      label: t("from"),
      value:
        start !== null
          ? `${clock(start)} – ${clock(start + spec.duration_s)}${spec.music_start_s == null ? ` · ${t("auto")}` : ""}`
          : t("auto"),
    },
    { icon: Film, label: t("clips"), value: String(spec.clip_count) },
  ];
  if (timings?.tempo_bpm) rows.push({ icon: Gauge, label: t("tempo"), value: `${Math.round(timings.tempo_bpm)} BPM` });
  if (timings?.cuts) rows.push({ icon: Scissors, label: t("cuts"), value: String(timings.cuts) });

  return (
    <Card className="flex flex-col gap-3 p-4">
      <span className="text-sm font-medium text-white/80">{t("title")}</span>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center gap-2 text-xs">
            <row.icon size={13} className="shrink-0 text-white/35" />
            <dt className="text-white/45">{row.label}</dt>
            <dd className="ml-auto truncate font-medium text-white/85">{row.value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-white/35">{t("note")}</p>
    </Card>
  );
}
