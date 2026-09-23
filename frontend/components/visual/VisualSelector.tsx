"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { Film, Image as ImageIcon, Clapperboard, TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { listVisualModes } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { VisualMode } from "@/lib/types";

// The mode names stay in English on purpose: they are what the API
// reports, what the pricing table is keyed on and what the landing page
// calls them. Only the sentence explaining each one is translated.
const OPTIONS: { mode: VisualMode; label: string; icon: typeof Film }[] = [
  { mode: "fast_hybrid", label: "Fast Hybrid", icon: ImageIcon },
  { mode: "ai_video", label: "AI Video", icon: Clapperboard },
  { mode: "stock_media", label: "Stock Media", icon: Film },
];

export function VisualSelector() {
  const t = useTranslations("studio.visual");
  const { draft, setDraft } = useShortPulseStore();
  // Undefined until the server answers. Everything is offered in the
  // meantime rather than nothing: a picker that starts empty and fills in
  // reads as broken, and the API refuses an unavailable mode anyway.
  const [availability, setAvailability] = useState<Record<string, string | null>>();

  useEffect(() => {
    listVisualModes()
      .then((modes) =>
        setAvailability(
          Object.fromEntries(modes.map((m) => [m.mode, m.available ? null : m.reason]))
        )
      )
      .catch(() => setAvailability(undefined));
  }, []);

  // A mode this install can't run still produces a video — the pipeline
  // falls back to stock footage — so an unavailable option isn't a broken
  // button, it's one that quietly delivers something else. On a paid
  // deployment it would also be charged at the higher rate.
  const blockedReason = (mode: VisualMode) => availability?.[mode] ?? null;

  useEffect(() => {
    // Nudge the selection off a mode that turns out to be unavailable —
    // fast_hybrid is the stored default, so most users would land on it.
    if (!availability) return;
    if (!blockedReason(draft.visualMode)) return;
    const usable = OPTIONS.find((o) => !blockedReason(o.mode));
    if (usable) setDraft({ visualMode: usable.mode, aiVideoAcknowledged: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availability]);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {OPTIONS.map(({ mode, label, icon: Icon }) => {
          const selected = draft.visualMode === mode;
          const blocked = blockedReason(mode);
          return (
            <button
              key={mode}
              type="button"
              disabled={Boolean(blocked)}
              title={blocked ?? undefined}
              onClick={() => setDraft({ visualMode: mode, aiVideoAcknowledged: mode === "ai_video" ? draft.aiVideoAcknowledged : false })}
              className={clsx(
                "flex flex-col items-start gap-2 rounded-lg border p-4 text-left transition-all duration-200",
                blocked
                  ? "cursor-not-allowed border-border bg-background opacity-40"
                  : selected
                    ? "border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                    : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
              )}
            >
              <Icon size={20} className={selected && !blocked ? "text-accent" : "text-white/60"} />
              <div className="text-sm font-medium">{label}</div>
              <div className="text-xs text-white/50">{blocked ?? t(mode)}</div>
            </button>
          );
        })}
      </div>

      {draft.visualMode === "ai_video" && (
        <div className="flex flex-col gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
          <div className="flex items-start gap-2 text-sm text-amber-200">
            <TriangleAlert size={16} className="mt-0.5 shrink-0" />
            <span>
              {t("aiWarning")}
            </span>
          </div>
          <label className="flex items-center gap-2 text-sm text-amber-100">
            <input
              type="checkbox"
              checked={draft.aiVideoAcknowledged}
              onChange={(e) => setDraft({ aiVideoAcknowledged: e.target.checked })}
              className="h-4 w-4 rounded border-border accent-amber-500"
            />
            {t("aiAck")}
          </label>
        </div>
      )}
    </div>
  );
}
