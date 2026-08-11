"use client";

import { useEffect, useState } from "react";
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
        Stock footage is filmed, not generated, so there&apos;s no art style to pick. Switch to Fast
        Hybrid or AI Video to choose one.
      </p>
    );
  }

  if (styles.length === 0) {
    return <p className="text-xs text-white/40">Loading styles...</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
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
