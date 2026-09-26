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
      {/* Stacked, not three across.
          `sm:grid-cols-3` asked the viewport how much room there was, and
          the answer had nothing to do with this control: it only ever
          renders inside the settings panel, which is 400px wide however
          wide the window is. Three columns of a 400px panel is 105px a
          tile, which is where a sentence of Turkish turns into eight
          lines and a compound noun hangs out of the box. One column is
          the honest shape for three text-heavy options. */}
      <div className="flex flex-col gap-2">
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
                // `items-start` used to sit here, which is what let the
                // text overflow: in a column flex it sizes every child to
                // its own content instead of the box, so a long word had
                // nothing to wrap against.
                "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-all duration-200",
                blocked
                  ? "cursor-not-allowed border-border bg-background opacity-40"
                  : selected
                    ? "border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                    : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
              )}
            >
              <Icon
                size={18}
                className={clsx(
                  "mt-0.5 shrink-0",
                  selected && !blocked ? "text-accent" : "text-white/60"
                )}
              />
              <div className="min-w-0">
                <div className="text-sm font-medium">{label}</div>
                {/* The mode's own sentence, always. This used to be
                    replaced by the API's reason when a mode was
                    unavailable — an English sentence written for whoever
                    runs the install, shown to a Turkish user in place of
                    the description, and long enough to double the height
                    of the row. It is still on the tooltip, where it was
                    meant to be. */}
                <div className="mt-0.5 break-words text-xs text-white/50">{t(mode)}</div>
                {blocked && (
                  <div className="mt-1 text-[11px] text-white/35">{t("unavailable")}</div>
                )}
              </div>
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
