"use client";

import { Shuffle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useShortPulseStore } from "@/lib/store";

/**
 * Topics that have actually been through this pipeline end to end — the
 * four on the landing page. Offering proven ones beats inventing
 * plausible-sounding prompts: a first render that comes out well is what
 * decides whether someone runs a second.
 */
const SUGGESTIONS = ["honey", "ocean", "cats", "sleep"] as const;

/**
 * Topic/script input. Users either type a topic (LLM writes the script)
 * or paste a raw script directly (LLM only segments it into scenes and
 * writes visual prompts — voiceover lines are left untouched).
 */
export function ScriptEditor() {
  const t = useTranslations("studio.script");
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-white/70">{t("topic")}</label>
        <input
          value={draft.topic}
          onChange={(e) => setDraft({ topic: e.target.value })}
          placeholder={t("topicPlaceholder")}
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
        />

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span className="flex items-center gap-1 text-[11px] text-white/30">
            <Shuffle size={11} />
            {t("try")}
          </span>
          {SUGGESTIONS.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setDraft({ topic: t(`suggestions.${id}`) })}
              className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-white/50 transition-colors hover:border-accent/50 hover:bg-accent/10 hover:text-white"
            >
              {t(`suggestions.${id}`)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-white/70">
          {t("rawScript")} <span className="text-white/40">{t("rawScriptHint")}</span>
        </label>
        <textarea
          value={draft.rawScript}
          onChange={(e) => setDraft({ rawScript: e.target.value })}
          placeholder={t("rawScriptPlaceholder")}
          rows={6}
          className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
        />
      </div>
    </div>
  );
}
