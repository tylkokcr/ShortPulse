"use client";

import clsx from "clsx";
import { useShortPulseStore } from "@/lib/store";
import type { AspectRatio } from "@/lib/types";

/**
 * `box` is the on-screen proportion of each preview rectangle — the same
 * shape the render will actually produce, since `aspect_ratio` now drives
 * the render target rather than being ignored.
 */
const OPTIONS: { ratio: AspectRatio; label: string; where: string; box: string }[] = [
  { ratio: "9:16", label: "9:16", where: "TikTok, Reels, Shorts", box: "h-9 w-[20px]" },
  { ratio: "1:1", label: "1:1", where: "Feed posts", box: "h-7 w-7" },
  { ratio: "16:9", label: "16:9", where: "YouTube, landscape", box: "h-[20px] w-9" },
];

export function AspectRatioSelector() {
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="grid grid-cols-3 gap-3">
      {OPTIONS.map(({ ratio, label, where, box }) => {
        const selected = draft.aspectRatio === ratio;
        return (
          <button
            key={ratio}
            type="button"
            onClick={() => setDraft({ aspectRatio: ratio })}
            className={clsx(
              "flex flex-col items-center gap-2 rounded-lg border px-3 py-3 transition-all duration-200",
              selected
                ? "border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
            )}
          >
            <span className="flex h-10 items-center justify-center">
              <span
                className={clsx(
                  "rounded-sm border-2 transition-colors",
                  box,
                  selected ? "border-accent" : "border-white/25"
                )}
              />
            </span>
            <span className="text-sm font-medium">{label}</span>
            <span className="text-center text-[11px] leading-tight text-white/40">{where}</span>
          </button>
        );
      })}
    </div>
  );
}
