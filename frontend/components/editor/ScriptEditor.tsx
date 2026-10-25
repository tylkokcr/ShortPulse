"use client";

import clsx from "clsx";
import { HelpCircle, PenLine, Shuffle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useShortPulseStore } from "@/lib/store";
import type { ScriptFormat } from "@/lib/types";

/**
 * Topics that have actually been through this pipeline end to end — the
 * four on the landing page. Offering proven ones beats inventing
 * plausible-sounding prompts: a first render that comes out well is what
 * decides whether someone runs a second.
 */
const SUGGESTIONS = ["honey", "ocean", "cats", "sleep"] as const;
const WHAT_IF_SUGGESTIONS = ["moon", "spin", "internet", "language"] as const;

/**
 * The kinds of video a topic can be written as. A format changes how the
 * script is written (see script_engine.FORMAT_RULES) and, as a shortcut,
 * picks the art style that suits it — a shortcut, not a lock: the style
 * can be changed afterwards like any other setting.
 */
const FORMATS: { id: ScriptFormat; icon: typeof PenLine; artStyle?: string }[] = [
  { id: "free", icon: PenLine },
  { id: "what_if", icon: HelpCircle, artStyle: "flat" },
];

/**
 * Topic/script input. Users either type a topic (LLM writes the script)
 * or paste a raw script directly (LLM only segments it into scenes and
 * writes visual prompts — voiceover lines are left untouched).
 */
export function ScriptEditor() {
  const t = useTranslations("studio.script");
  const { draft, setDraft } = useShortPulseStore();
  const whatIf = draft.scriptFormat === "what_if";
  const suggestions = whatIf ? WHAT_IF_SUGGESTIONS : SUGGESTIONS;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <span className="mb-1.5 block text-sm font-medium text-white/70">{t("format")}</span>
        <div className="flex flex-wrap gap-2">
          {FORMATS.map((format) => (
            <button
              key={format.id}
              type="button"
              onClick={() =>
                setDraft({
                  scriptFormat: format.id,
                  ...(format.artStyle ? { artStyle: format.artStyle } : {}),
                })
              }
              aria-pressed={draft.scriptFormat === format.id}
              className={clsx(
                "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                draft.scriptFormat === format.id
                  ? "border-accent/60 bg-accent/[0.08] text-white"
                  : "border-border text-white/50 hover:border-border-strong"
              )}
            >
              <format.icon size={12} />
              {t(`formats.${format.id}.name`)}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-white/40">{t(`formats.${draft.scriptFormat}.hint`)}</p>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-white/70">{t("topic")}</label>
        <input
          value={draft.topic}
          onChange={(e) => setDraft({ topic: e.target.value })}
          placeholder={whatIf ? t("whatIfPlaceholder") : t("topicPlaceholder")}
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
        />

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span className="flex items-center gap-1 text-[11px] text-white/30">
            <Shuffle size={11} />
            {t("try")}
          </span>
          {suggestions.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setDraft({ topic: t(`${whatIf ? "whatIfSuggestions" : "suggestions"}.${id}`) })}
              className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-white/50 transition-colors hover:border-accent/50 hover:bg-accent/10 hover:text-white"
            >
              {t(`${whatIf ? "whatIfSuggestions" : "suggestions"}.${id}`)}
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
