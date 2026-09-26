"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";
import { CAPTION_FONT_VARS } from "@/lib/captionFonts";
import { CaptionPreview } from "./CaptionStyleSelector";
import { CLIP_TEMPLATES, type ClipTemplate } from "@/lib/clipTemplates";
import { presetById } from "@/lib/captionStyles";
import type { SubtitleStyle } from "@/lib/types";

/**
 * Pick the whole look in one tap.
 *
 * A grid rather than the carousel Opus uses: six tiles fit on one screen,
 * and a grid is what every other catalogue in this app is drawn as — the
 * caption styles, the art styles, the visual modes. A carousel would hide
 * half the options behind a gesture to save space that is not short.
 *
 * The tile shows the real caption preview, the same component the caption
 * picker uses, so what it promises is what libass will draw — including
 * the position, which the preview already honours. The frame is a chip
 * rather than a second preview: a 1:1 and a 9:16 thumbnail at this size
 * differ by a few pixels and would read as a rendering glitch.
 */
export function ClipTemplateSelector({
  selected,
  onSelect,
  framesAllowed,
  className,
}: {
  /** Nothing is selected until the user picks one — a template is a
   *  shortcut, not a default that silently applied. */
  selected: string | null;
  onSelect: (template: ClipTemplate) => void;
  /** False when captioning whole, where the API refuses any frame but the
   *  original. The tiles that would be refused say so instead of failing
   *  on submit. */
  framesAllowed: boolean;
  className?: string;
}) {
  const t = useTranslations("studio.upload");

  return (
    <div className={className}>
      <span className="mb-1.5 block text-sm font-medium text-white/70">{t("template")}</span>
      {/* Two columns, fixed. `sm:grid-cols-3` asked the window how
          much room there was, and the answer stopped being relevant
          when this moved into the settings drawer: that is 384-400px
          whatever the window is, so three columns meant 115px tiles
          with an eight-line description under each. */}
      <div className={clsx("grid grid-cols-2 gap-3", CAPTION_FONT_VARS)}>
        {CLIP_TEMPLATES.map((template) => {
          const preset = presetById(template.captionPreset);
          const blocked = !framesAllowed && template.aspectRatio !== "9:16";
          const isSelected = selected === template.id;

          return (
            <button
              key={template.id}
              type="button"
              disabled={blocked}
              onClick={() => onSelect(template)}
              title={blocked ? t("templateNeedsClips") : undefined}
              className={clsx(
                "flex flex-col gap-2 rounded-lg border p-3 text-left transition-all duration-200",
                blocked
                  ? "cursor-not-allowed border-border bg-surface opacity-40"
                  : isSelected
                    ? "-translate-y-0.5 border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                    : "border-border bg-surface hover:-translate-y-0.5 hover:border-border-strong hover:bg-surface-hover"
              )}
            >
              <CaptionPreview preset={{ ...preset, style: previewStyle(template, preset.style) }} />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium">{template.name}</span>
                  <span className="rounded border border-border px-1 font-mono text-[9px] text-white/35">
                    {template.aspectRatio}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] leading-snug text-white/40">
                  {template.description}
                </div>
              </div>
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 text-xs text-white/40">
        {framesAllowed ? t("templateHint") : t("templateNeedsClips")}
      </p>
    </div>
  );
}

/** The preview has to show the template's placement, not the preset's —
 *  otherwise two templates built on the same preset look identical. */
function previewStyle(template: ClipTemplate, base: SubtitleStyle): SubtitleStyle {
  return {
    ...base,
    position: template.captionPosition,
    font_size: template.captionFontSize ?? base.font_size,
  };
}
