"use client";

import clsx from "clsx";
import { Film, Image as ImageIcon, Clapperboard, TriangleAlert } from "lucide-react";
import { useShortPulseStore } from "@/lib/store";
import type { VisualMode } from "@/lib/types";

const OPTIONS: { mode: VisualMode; label: string; description: string; icon: typeof Film }[] = [
  {
    mode: "fast_hybrid",
    label: "Fast Hybrid",
    description: "AI stills + Ken Burns pan/zoom. Recommended — fast on modest hardware.",
    icon: ImageIcon,
  },
  {
    mode: "ai_video",
    label: "AI Video",
    description: "Local text-to-video diffusion. Slowest, needs a real GPU.",
    icon: Clapperboard,
  },
  {
    mode: "stock_media",
    label: "Stock Media",
    description: "Free Pexels/Pixabay footage. Zero GPU required.",
    icon: Film,
  },
];

export function VisualSelector() {
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {OPTIONS.map(({ mode, label, description, icon: Icon }) => {
          const selected = draft.visualMode === mode;
          return (
            <button
              key={mode}
              type="button"
              onClick={() => setDraft({ visualMode: mode, aiVideoAcknowledged: mode === "ai_video" ? draft.aiVideoAcknowledged : false })}
              className={clsx(
                "flex flex-col items-start gap-2 rounded-lg border p-4 text-left transition-colors",
                selected ? "border-accent bg-accent/10" : "border-border bg-background hover:bg-surface-hover"
              )}
            >
              <Icon size={20} className={selected ? "text-accent" : "text-white/60"} />
              <div className="text-sm font-medium">{label}</div>
              <div className="text-xs text-white/50">{description}</div>
            </button>
          );
        })}
      </div>

      {draft.visualMode === "ai_video" && (
        <div className="flex flex-col gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
          <div className="flex items-start gap-2 text-sm text-amber-200">
            <TriangleAlert size={16} className="mt-0.5 shrink-0" />
            <span>
              AI Video downloads a large model (tens of GB) the first time you use it on a
              machine — this can take hours on a slow connection, and generation itself is slow
              without a real GPU. It&apos;s a one-time download; later renders won&apos;t repeat it.
            </span>
          </div>
          <label className="flex items-center gap-2 text-sm text-amber-100">
            <input
              type="checkbox"
              checked={draft.aiVideoAcknowledged}
              onChange={(e) => setDraft({ aiVideoAcknowledged: e.target.checked })}
              className="h-4 w-4 rounded border-border accent-amber-500"
            />
            I understand this may take a long time on first use
          </label>
        </div>
      )}
    </div>
  );
}
