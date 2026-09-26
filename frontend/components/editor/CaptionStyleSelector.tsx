"use client";

import clsx from "clsx";
import { CAPTION_PRESETS, type CaptionPreset } from "@/lib/captionStyles";
import { CAPTION_FONT_VARS } from "@/lib/captionFonts";
import { LANGUAGE_OPTIONS } from "@/lib/types";
import { useShortPulseStore } from "@/lib/store";

export function CaptionStyleSelector() {
  const { draft, setDraft } = useShortPulseStore();
  const languageLabel =
    LANGUAGE_OPTIONS.find((option) => option.code === draft.language)?.label ?? draft.language;

  return (
    // The font variables hang here so every preview below resolves them.
    //
    // Two columns, not four. These live in the 400px settings drawer on
    // both studio tabs; `sm:grid-cols-4` was measuring the window and
    // giving each preset 85px to show a caption in.
    <div className={clsx("grid grid-cols-2 gap-3", CAPTION_FONT_VARS)}>
      {CAPTION_PRESETS.map((preset) => {
        const selected = draft.captionPreset === preset.id;
        return (
          <button
            key={preset.id}
            type="button"
            onClick={() => setDraft({ captionPreset: preset.id })}
            className={clsx(
              "flex flex-col gap-2 rounded-lg border p-3 text-left transition-all duration-200",
              selected
                ? // Ring, tint and a small lift together — a border alone
                  // was doing all the work and losing at a glance against
                  // eleven other bordered things on the same screen.
                  "-translate-y-0.5 border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                : // bg-surface, not bg-background: an option drawn darker
                  // than the panel it sits in reads as a hole rather than
                  // as a card, which is most of why this grid looked flat.
                  "border-border bg-surface hover:-translate-y-0.5 hover:border-border-strong hover:bg-surface-hover"
            )}
          >
            <CaptionPreview preset={preset} />
            <div>
              <div className="text-xs font-medium">{preset.name}</div>
              <div className="mt-0.5 text-[11px] leading-snug text-white/40">
                {preset.description}
              </div>
              {/* Said here rather than discovered in the finished video.
                  The render substitutes a face that can draw the
                  language, which is the right thing to do and a
                  surprising one to find out afterwards. */}
              {preset.notCovered?.includes(draft.language) && (
                <div className="mt-1 text-[11px] leading-snug text-amber-400/80">
                  Not available in {languageLabel} — this one keeps the default lettering.
                </div>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Approximates the burned-in result in HTML: same word count per line,
 * same casing, same highlight colour, and the caption sits where
 * `position` will put it. It can't be pixel-exact — libass renders
 * Montserrat with a real outline — but it gets the decision right.
 */
export function CaptionPreview({
  preset,
  className,
}: {
  preset: CaptionPreset;
  className?: string;
}) {
  const words = ["this", "is", "how", "it", "looks"].slice(0, preset.style.max_words_per_line);
  const activeIndex = 1;

  const justify =
    preset.style.position === "middle"
      ? "items-center"
      : preset.style.position === "top_third"
        ? "items-start"
        : "items-end";

  return (
    <div
      className={clsx(
        // Lighter than it was. These previews stand in for a video frame,
        // and a near-black one gives white captions with a black outline
        // nothing to sit against — the styles all looked identical because
        // the only thing separating them was invisible.
        "flex aspect-[4/3] w-full justify-center overflow-hidden rounded-md bg-gradient-to-br from-neutral-500 via-neutral-700 to-neutral-800 p-2",
        justify,
        className
      )}
    >
      <p
        className={clsx(
          "text-center font-extrabold leading-tight",
          preset.style.uppercase ? "uppercase" : "normal-case",
          preset.style.font_size >= 90
            ? "text-[11px]"
            : preset.style.font_size >= 84
              ? "text-[10px]"
              : "text-[9px]"
        )}
        style={{
          // The real face, loaded through next/font — a preview in Arial
          // claiming to be Anton is worse than no preview.
          fontFamily: preset.previewFont,
          ...(preset.style.box
            ? // A filled strip, so no stroke to imitate. The words sit on
              // it as one run rather than as separate chips, which is how
              // libass draws a boxed line.
              { backgroundColor: preset.previewBox, boxShadow: `0 0 0 2px ${preset.previewBox}` }
            : {
                // Stand-in for the ASS outline, which is a stroke around
                // glyphs rather than a drop shadow.
                textShadow: `0 0 ${preset.style.outline_width}px #000, 0 1px 2px #000`,
              }),
        }}
      >
        {words.map((word, i) => {
          const active = i === activeIndex;
          return (
            <span
              key={word}
              style={
                preset.style.box
                  ? {
                      // The active word's *block* changes, not its
                      // letters — the same swap the renderer makes.
                      color: preset.previewText ?? "#fff",
                      backgroundColor: active ? preset.previewHighlight : undefined,
                    }
                  : { color: active ? preset.previewHighlight : "#fff" }
              }
            >
              {word}
              {i < words.length - 1 ? " " : ""}
            </span>
          );
        })}
      </p>
    </div>
  );
}
