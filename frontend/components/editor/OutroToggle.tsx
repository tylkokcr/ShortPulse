"use client";

import { useTranslations } from "next-intl";
import { useShortPulseStore } from "@/lib/store";

/**
 * Optional branded closing card, drawn locally (no AI generation) instead
 * of leaving the final scene's visual up to whatever the LLM imagined for
 * the call-to-action.
 */
export function OutroToggle() {
  const t = useTranslations("studio.outro");
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="flex flex-col gap-3">
      <label className="flex cursor-pointer items-center gap-2 text-sm text-white/80">
        <input
          type="checkbox"
          checked={draft.outroEnabled}
          onChange={(e) => setDraft({ outroEnabled: e.target.checked })}
          className="h-4 w-4 rounded border-border accent-accent"
        />
        {t("toggle")}
      </label>

      {draft.outroEnabled && (
        <input
          value={draft.outroText}
          onChange={(e) => setDraft({ outroText: e.target.value })}
          placeholder={t("placeholder")}
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent animate-fade-in"
        />
      )}
    </div>
  );
}
