"use client";

import { useShortPulseStore } from "@/lib/store";
import { useTranslations } from "next-intl";

/**
 * What to keep out of every generated frame.
 *
 * Before the render rather than after, because that is the only point at
 * which it prevents anything. A scene can be re-rolled with its own
 * additions later, but by then the picture that prompted it has already
 * been drawn and paid for.
 *
 * Adds to the art style's own exclusions rather than replacing them — the
 * style carries twenty terms about anatomy, crowds and on-screen text that
 * a one-word entry here must not silently switch off. See
 * visual_engine.negative_for.
 */
// Not translated, and they must not be: these are prompt tokens, joined
// onto the art style's own English negative prompt and handed to the
// image model (see visual_engine.negative_for). "eller" excludes nothing.
const SUGGESTIONS = ["hands", "crowd", "text", "logos", "children"];

export function NegativePrompt() {
  const t = useTranslations("studio.negative");
  const { draft, setDraft } = useShortPulseStore();

  // Nothing to exclude from footage somebody else filmed — same reason
  // the art style picker doesn't apply to it.
  if (draft.visualMode === "stock_media") {
    return (
      <p className="text-xs leading-relaxed text-white/30">
        {t("stockNotice")}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        value={draft.negativePrompt}
        onChange={(e) => setDraft({ negativePrompt: e.target.value })}
        maxLength={400}
        placeholder="hands, crowd, text"
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-border-strong"
      />

      <div className="flex flex-wrap items-center gap-1.5">
        {SUGGESTIONS.map((term) => {
          const terms = draft.negativePrompt
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean);
          const on = terms.some((t) => t.toLowerCase() === term);
          return (
            <button
              key={term}
              type="button"
              onClick={() =>
                setDraft({
                  negativePrompt: (on
                    ? terms.filter((t) => t.toLowerCase() !== term)
                    : [...terms, term]
                  ).join(", "),
                })
              }
              className={
                on
                  ? "rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[10px] text-accent"
                  : "rounded-md border border-border px-2 py-0.5 font-mono text-[10px] text-white/40 transition-colors hover:border-border-strong hover:text-white/70"
              }
            >
              {term}
            </button>
          );
        })}
      </div>

      <p className="text-[11px] leading-relaxed text-white/30">
        {t("hint")} {t("englishNote")}
      </p>
    </div>
  );
}
