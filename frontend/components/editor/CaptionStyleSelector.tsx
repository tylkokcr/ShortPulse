"use client";

import clsx from "clsx";
import { CAPTION_PRESETS, type CaptionPreset } from "@/lib/captionStyles";
import { useShortPulseStore } from "@/lib/store";

export function CaptionStyleSelector() {
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
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
                ? "border-accent bg-accent/10 shadow-[0_0_0_1px] shadow-accent/40"
                : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
            )}
          >
            <CaptionPreview preset={preset} />
            <div>
              <div className="text-xs font-medium">{preset.name}</div>
              <div className="mt-0.5 text-[11px] leading-snug text-white/40">
                {preset.description}
              </div>
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
        "flex aspect-[4/3] w-full justify-center overflow-hidden rounded-md bg-gradient-to-br from-neutral-700 via-neutral-800 to-neutral-900 p-2",
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
          // Stand-in for the ASS outline, which is a stroke around glyphs
          // rather than a drop shadow.
          textShadow: `0 0 ${preset.style.outline_width}px #000, 0 1px 2px #000`,
        }}
      >
        {words.map((word, i) => (
          <span
            key={word}
            style={{ color: i === activeIndex ? preset.previewHighlight : "#fff" }}
          >
            {word}
            {i < words.length - 1 ? " " : ""}
          </span>
        ))}
      </p>
    </div>
  );
}
