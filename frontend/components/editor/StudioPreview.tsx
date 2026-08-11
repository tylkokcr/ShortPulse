"use client";

import clsx from "clsx";
import { useShortPulseStore } from "@/lib/store";
import { presetById } from "@/lib/captionStyles";
import type { AspectRatio } from "@/lib/types";

/**
 * A live composite of the choices made so far.
 *
 * Nothing here is decorative: the frame takes the selected aspect ratio's
 * real proportions, the backdrop is the actual sample frame for the chosen
 * art style, and the caption is drawn from the same preset the renderer
 * burns in — word count per line, casing, highlight colour and vertical
 * placement included. Changing a control changes this, which is the point:
 * a form tells you what you picked, a preview shows you.
 *
 * It is a preview, not the render. `PREVIEW_CAPTION` stands in for a line
 * the script hasn't written yet.
 */
const ASPECT_CLASS: Record<AspectRatio, string> = {
  "9:16": "aspect-[9/16] max-w-[210px]",
  "1:1": "aspect-square max-w-[280px]",
  "16:9": "aspect-video max-w-[320px]",
};

const PREVIEW_CAPTION = ["your", "words", "land", "on", "the", "beat"];

export function StudioPreview() {
  const { draft } = useShortPulseStore();
  const preset = presetById(draft.captionPreset);
  const perLine = preset.style.max_words_per_line;

  const lines: string[][] = [];
  for (let i = 0; i < PREVIEW_CAPTION.length; i += perLine) {
    lines.push(PREVIEW_CAPTION.slice(i, i + perLine));
  }

  const placement =
    preset.style.position === "middle"
      ? "items-center"
      : preset.style.position === "top_third"
        ? "items-start"
        : "items-end";

  // Stock footage has no art style, so there's no representative frame to
  // show — a style sample there would promise a look it won't deliver.
  const backdrop =
    draft.visualMode === "stock_media" ? null : `/art-styles/${draft.artStyle}.jpg`;

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className={clsx(
          "relative w-full overflow-hidden rounded-md border border-border-strong bg-neutral-900 shadow-2xl shadow-black/50 transition-all duration-300",
          ASPECT_CLASS[draft.aspectRatio],
          placement,
          "flex justify-center"
        )}
      >
        {backdrop ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={backdrop}
            src={backdrop}
            alt=""
            aria-hidden
            className="absolute inset-0 h-full w-full object-cover animate-fade-in"
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-neutral-700 via-neutral-800 to-neutral-900" />
        )}

        {/* Keeps captions readable over a bright frame, exactly as the
            burned-in outline does in the real render. */}
        <div className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-black/70 to-transparent" />

        <p
          className={clsx(
            "relative z-10 px-3 pb-4 text-center font-extrabold leading-tight",
            preset.style.uppercase ? "uppercase" : "normal-case",
            draft.aspectRatio === "16:9" ? "text-[11px]" : "text-xs"
          )}
          style={{ textShadow: `0 0 ${preset.style.outline_width}px #000, 0 1px 3px #000` }}
        >
          {lines.map((line, li) => (
            <span key={li} className="block">
              {line.map((word, wi) => (
                <span
                  key={`${li}-${word}`}
                  style={{ color: wi === (li === 0 ? 1 : 0) ? preset.previewHighlight : "#fff" }}
                >
                  {word}{" "}
                </span>
              ))}
            </span>
          ))}
        </p>
      </div>

      <p className="text-center font-mono text-[10px] leading-relaxed text-white/30">
        Preview — caption style and frame are live, the footage is a style sample.
      </p>
    </div>
  );
}
