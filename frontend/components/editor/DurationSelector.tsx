"use client";

import clsx from "clsx";
import { useShortPulseStore } from "@/lib/store";
import type { VideoLength } from "@/lib/types";

const OPTIONS: { length: VideoLength; label: string; description: string }[] = [
  { length: "short", label: "Short", description: "~15-25s, 5-6 scenes" },
  { length: "medium", label: "Medium", description: "~30-45s, 8-10 scenes" },
  { length: "long", label: "Long", description: "~60s+, 12-15 scenes" },
];

export function DurationSelector() {
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="grid grid-cols-3 gap-3">
      {OPTIONS.map(({ length, label, description }) => {
        const selected = draft.videoLength === length;
        return (
          <button
            key={length}
            type="button"
            onClick={() => setDraft({ videoLength: length })}
            className={clsx(
              "flex flex-col items-center gap-1 rounded-lg border px-3 py-3 text-center transition-colors",
              selected ? "border-accent bg-accent/10" : "border-border bg-background hover:bg-surface-hover"
            )}
          >
            <span className="text-sm font-medium">{label}</span>
            <span className="text-xs text-white/50">{description}</span>
          </button>
        );
      })}
    </div>
  );
}
