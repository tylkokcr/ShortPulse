"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Check } from "lucide-react";
import clsx from "clsx";
import { listArtStyles } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { ArtStyle } from "@/lib/types";

/**
 * Art style picker.
 *
 * Every thumbnail is a real render from this pipeline — same checkpoint,
 * same settings, same subject prompt — so the card shows what the setting
 * actually does instead of an artist's impression of it.
 *
 * Hidden for stock footage, which has no style to choose: those clips are
 * whatever the videographer filmed.
 */
export function ArtStyleSelector() {
  const t = useTranslations("studio.artStyle");
  const { draft, setDraft } = useShortPulseStore();
  const [styles, setStyles] = useState<ArtStyle[]>([]);

  useEffect(() => {
    listArtStyles()
      .then(setStyles)
      .catch(() => setStyles([]));
  }, []);

  if (draft.visualMode === "stock_media") {
    return (
      <p className="text-[11px] leading-relaxed text-white/30">
        {t("stockNotice")}
      </p>
    );
  }

  if (styles.length === 0) {
    return <p className="text-xs text-white/40">{t("loading")}</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Two columns below 380px. Three of them leaves a 52px tile, and the
          style names are single words — "Claymation" is 65px and cannot
          wrap, so it spills out of its own button on a 320px phone. */}
      {/* Three at most. Six columns of the 400px drawer is a 55px
          thumbnail with "Claymation" wrapped under it — the window
          this was sized against is not the box it renders in. */}
      <div className="grid grid-cols-2 gap-3 min-[380px]:grid-cols-3">
        {styles.map((style) => {
          const selected = draft.artStyle === style.id;
          return (
            <button
              key={style.id}
              type="button"
              onClick={() => setDraft({ artStyle: style.id })}
              title={style.description}
              className={clsx(
                "group flex flex-col gap-2 rounded-lg border p-1.5 text-left transition-all duration-200",
                selected
                  ? "border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                  : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
              )}
            >
              <span className="relative block overflow-hidden rounded-md">
                {/* Plain <img>: these are small local files, and next/image
                    would add a loader for no benefit here. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/art-styles/${style.sample}`}
                  alt={`${style.name} example frame`}
                  loading="lazy"
                  className="aspect-[9/16] w-full object-cover transition-transform duration-300 group-hover:scale-105"
                />
                {selected && (
                  <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent">
                    <Check size={10} className="text-white" />
                  </span>
                )}
              </span>
              <span className="px-0.5 pb-0.5 text-[11px] font-medium leading-tight">
                {style.name}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-[11px] leading-relaxed text-white/30">
        {styles.find((style) => style.id === draft.artStyle)?.description}
      </p>
    </div>
  );
}
