"use client";

import { useState } from "react";
import { BadgeCheck, LayoutList, Map as MapIcon, Mic, Volume2, VolumeX } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

/**
 * The "what if?" format, played: one finished video per page language, and
 * the other three a tap away.
 *
 * Each is real output of the live service — a topic typed into the studio
 * in that language, the script written from checked facts, countries drawn
 * from Natural Earth outlines, the AI stills generated, narrated and
 * graphed by the pipeline — with nothing edited afterwards. Like the other
 * showcase videos they live in public/showcase and are not in git (see
 * public/examples/README.md for getting them onto the server).
 */
const VIDEOS = [
  { code: "tr", label: "Türkiye", src: "/showcase/whatif-tr.mp4", poster: "/showcase/whatif-tr.jpg" },
  { code: "en", label: "The Moon", src: "/showcase/whatif-en.mp4", poster: "/showcase/whatif-en.jpg" },
  { code: "pl", label: "Polska", src: "/showcase/whatif-pl.mp4", poster: "/showcase/whatif-pl.jpg" },
  { code: "de", label: "Deutschland", src: "/showcase/whatif-de.mp4", poster: "/showcase/whatif-de.jpg" },
] as const;

const POINTS = [
  { key: "maps", icon: MapIcon },
  { key: "facts", icon: BadgeCheck },
  { key: "graphics", icon: LayoutList },
  { key: "voice", icon: Mic },
] as const;

export function WhatIfShowcase() {
  const t = useTranslations("landing.whatIf");
  const ts = useTranslations("showcase");
  const locale = useLocale();
  const [current, setCurrent] = useState<string>(
    VIDEOS.find((v) => v.code === locale)?.code ?? "en"
  );
  const [muted, setMuted] = useState(true);
  const video = VIDEOS.find((v) => v.code === current) ?? VIDEOS[1];

  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex flex-col gap-5">
          <Badge tone="accent" className="w-fit">
            {t("badge")}
          </Badge>
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
          <p className="max-w-xl text-sm leading-relaxed text-white/55">{t("sub")}</p>
          <ul className="flex flex-col gap-3">
            {POINTS.map(({ key, icon: Icon }) => (
              <li key={key} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent/15 text-accent">
                  <Icon size={14} />
                </span>
                <span className="text-sm leading-relaxed text-white/70">{t(`points.${key}`)}</span>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-xs text-white/40">{t("examples")}</span>
            {VIDEOS.map((v) => (
              <button
                key={v.code}
                type="button"
                onClick={() => setCurrent(v.code)}
                aria-pressed={current === v.code}
                className={
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors " +
                  (current === v.code
                    ? "border-accent bg-accent/15 text-white"
                    : "border-border text-white/55 hover:border-border-strong hover:text-white")
                }
              >
                {v.label}
              </button>
            ))}
          </div>
          <Link href="/login" className="w-fit">
            <Button>{t("cta")}</Button>
          </Link>
        </div>

        <div className="relative mx-auto aspect-[9/16] w-[230px] shrink-0 overflow-hidden rounded-[26px] border border-border-strong bg-black shadow-2xl shadow-black/60 sm:w-[270px]">
          <video
            key={video.src}
            src={video.src}
            poster={video.poster}
            autoPlay
            loop
            muted={muted}
            playsInline
            preload="metadata"
            className="h-full w-full object-cover"
          />
          <button
            type="button"
            onClick={() => setMuted((m) => !m)}
            aria-label={ts(muted ? "soundOn" : "soundOff")}
            className="absolute bottom-3 right-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white/80 backdrop-blur hover:text-white"
          >
            {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
          </button>
        </div>
      </div>
    </section>
  );
}
