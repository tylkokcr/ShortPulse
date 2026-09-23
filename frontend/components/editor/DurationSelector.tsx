"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";
import { useShortPulseStore } from "@/lib/store";
import type { VideoLength } from "@/lib/types";

const OPTIONS: VideoLength[] = ["short", "medium", "long"];

export function DurationSelector() {
  const t = useTranslations("studio");
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="grid grid-cols-3 gap-3">
      {OPTIONS.map((length) => {
        const selected = draft.videoLength === length;
        return (
          <button
            key={length}
            type="button"
            onClick={() => setDraft({ videoLength: length })}
            className={clsx(
              "flex flex-col items-center gap-1 rounded-lg border px-3 py-3 text-center transition-all duration-200",
              selected
                ? "border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
            )}
          >
            <span className="text-sm font-medium">{t(`length.${length}`)}</span>
            <span className="text-xs text-white/50">{t(`duration.${length}`)}</span>
          </button>
        );
      })}
    </div>
  );
}
