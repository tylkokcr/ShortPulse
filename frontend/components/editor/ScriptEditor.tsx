"use client";

import clsx from "clsx";
import { Clapperboard, PenLine, Shuffle } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { listVisualModes } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { ScriptFormat, VideoLength } from "@/lib/types";

/**
 * Topics that have actually been through this pipeline end to end — the
 * four on the landing page. Offering proven ones beats inventing
 * plausible-sounding prompts: a first render that comes out well is what
 * decides whether someone runs a second.
 */
const SUGGESTIONS: Record<ScriptFormat, readonly string[]> = {
  free: ["honey", "ocean", "cats", "sleep"],
  what_if: ["moon", "spin", "internet", "language"],
  outbreak: ["city", "school", "island", "metro"],
  story: ["kitchen", "neighbour", "letter", "basement"],
};
// The messages key each format's suggestions and placeholder live under.
const SUGGESTION_KEYS: Record<ScriptFormat, string> = {
  free: "suggestions",
  what_if: "whatIfSuggestions",
  outbreak: "outbreakSuggestions",
  story: "storySuggestions",
};
const PLACEHOLDERS: Record<ScriptFormat, string> = {
  free: "topicPlaceholder",
  what_if: "whatIfPlaceholder",
  outbreak: "outbreakPlaceholder",
  story: "storyPlaceholder",
};

/**
 * The kinds of video a topic can be written as. A format changes how the
 * script is written (see script_engine.FORMAT_RULES) and, as a shortcut,
 * picks the art style that suits it — a shortcut, not a lock: the style
 * can be changed afterwards like any other setting. Leaving the format
 * takes its style back with it, unless the style was changed meanwhile:
 * otherwise "free" kept the cartoon look and its preview.
 */
const FORMATS: {
  id: ScriptFormat;
  icon: typeof PenLine;
  artStyle?: string;
  videoLength?: VideoLength;
  // Moving pictures by default, where this install animates over an API.
  animated?: boolean;
}[] = [
  { id: "free", icon: PenLine },
  // The series formats (outbreak, story) are started from app/series.
];

const DEFAULT_ART_STYLE = useShortPulseStore.getInitialState().draft.artStyle;
const DEFAULT_VIDEO_LENGTH = useShortPulseStore.getInitialState().draft.videoLength;

/**
 * Topic/script input. Users either type a topic (LLM writes the script)
 * or paste a raw script directly (LLM only segments it into scenes and
 * writes visual prompts — voiceover lines are left untouched).
 */
export function ScriptEditor() {
  const t = useTranslations("studio.script");
  const { draft, setDraft } = useShortPulseStore();
  const suggestions = SUGGESTIONS[draft.scriptFormat];
  const suggestionKey = SUGGESTION_KEYS[draft.scriptFormat];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <span className="mb-1.5 block text-sm font-medium text-white/70">{t("format")}</span>
        <div className="flex flex-wrap gap-2">
          {FORMATS.map((format) => (
            <button
              key={format.id}
              type="button"
              onClick={() => {
                const leaving = FORMATS.find((f) => f.id === draft.scriptFormat);
                const artStyle =
                  format.artStyle ??
                  (leaving?.artStyle && leaving.artStyle === draft.artStyle ? DEFAULT_ART_STYLE : undefined);
                // The length a format chose goes back with it too, unless
                // it was changed meanwhile.
                const videoLength =
                  format.videoLength ??
                  (leaving?.videoLength && leaving.videoLength === draft.videoLength
                    ? DEFAULT_VIDEO_LENGTH
                    : undefined);
                setDraft({
                  scriptFormat: format.id,
                  ...(artStyle ? { artStyle } : {}),
                  ...(videoLength ? { videoLength } : {}),
                  // Leaving an animated-by-default format takes the
                  // animation back with it.
                  ...(leaving?.animated && !format.animated && draft.visualMode === "ai_video"
                    ? { visualMode: "fast_hybrid" as const, aiVideoAcknowledged: false }
                    : {}),
                });
                if (format.animated) {
                  // A story without motion looked like a slideshow. Only
                  // where animation runs over an API: on a local GPU it
                  // means a tens-of-GB download nobody asked for.
                  listVisualModes()
                    .then((modes) => {
                      const hosted = modes.some(
                        (m) => m.mode === "ai_video" && m.available && m.backend === "replicate"
                      );
                      if (hosted) setDraft({ visualMode: "ai_video", aiVideoAcknowledged: true });
                    })
                    .catch(() => {});
                }
              }}
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
        {/* Series are made in episodes and have their own place. */}
        <Link
          href="/series"
          className="mt-2 inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
        >
          <Clapperboard size={12} />
          {t("seriesLink")}
        </Link>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-white/70">{t("topic")}</label>
        <input
          value={draft.topic}
          onChange={(e) => setDraft({ topic: e.target.value })}
          placeholder={t(PLACEHOLDERS[draft.scriptFormat])}
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
              onClick={() => setDraft({ topic: t(`${suggestionKey}.${id}`) })}
              className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-white/50 transition-colors hover:border-accent/50 hover:bg-accent/10 hover:text-white"
            >
              {t(`${suggestionKey}.${id}`)}
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
