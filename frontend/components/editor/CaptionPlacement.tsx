"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";
import { CAPTION_POSITIONS, CAPTION_SIZES, sizeIdFor } from "@/lib/captionStyles";
import type { SubtitleStyle } from "@/lib/types";

/**
 * Where the captions sit, and how big.
 *
 * Split out of the preset picker on purpose. A preset is a look — font,
 * colour, box, highlight — and someone who wants the words higher up does
 * not want a different typeface to arrive with that choice. Keeping them
 * apart also means the two fields survive switching preset, which is what
 * anyone would expect and what merging them into the preset list could
 * not do.
 *
 * Used before the render and again after it. The second one is not a
 * duplicate: `editing.py` re-burns from `EditSpec.captions.style`, so
 * changing placement on a finished video is one ffmpeg pass rather than a
 * re-render — and placement is exactly the thing you only notice once you
 * are watching it over the actual footage.
 *
 * Controlled rather than reading the store itself, because the editor
 * edits a project's stored style and the studio edits the draft. Same
 * control, two different owners.
 */
export function CaptionPlacement({
  position,
  fontSize,
  onChange,
  className,
}: {
  position: SubtitleStyle["position"];
  /** The size actually in effect — the preset's own where the viewer has
   *  not chosen one, so the control always shows where they stand. */
  fontSize: number;
  onChange: (next: { position: SubtitleStyle["position"]; fontSize: number }) => void;
  className?: string;
}) {
  const selectedSize = sizeIdFor(fontSize);
  const t = useTranslations("studio.captionPlacement");

  return (
    <div className={clsx("flex flex-col gap-3", className)}>
      <Row label={t("position")}>
        {CAPTION_POSITIONS.map((option) => (
          <Choice
            key={option}
            selected={position === option}
            onClick={() => onChange({ position: option, fontSize })}
            title={t(`positions.${option}`)}
          >
            {/* The shape, not the word: the choice is about where in the
                frame, and a 9:16 rectangle with a bar in it says that
                faster than three labels do. */}
            <span className="relative block h-7 w-[16px] overflow-hidden rounded-[3px] border border-white/15 bg-black/50">
              <span
                className={clsx(
                  "absolute inset-x-[2px] h-[3px] rounded-[1px] bg-current",
                  option === "top_third" && "top-[4px]",
                  option === "middle" && "top-1/2 -translate-y-1/2",
                  option === "bottom_third" && "bottom-[4px]"
                )}
              />
            </span>
          </Choice>
        ))}
      </Row>

      <Row label={t("size")}>
        {CAPTION_SIZES.map((step) => (
          <Choice
            key={step.id}
            selected={selectedSize === step.id}
            onClick={() => onChange({ position, fontSize: step.px })}
            title={t(`sizes.${step.id}`)}
          >
            <span className="px-1 text-[11px] font-semibold leading-none">
              {t(`sizes.${step.id}`)}
            </span>
          </Choice>
        ))}
      </Row>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-[72px] shrink-0 text-[11px] text-white/40">{label}</span>
      <div className="flex items-center gap-1.5">{children}</div>
    </div>
  );
}

function Choice({
  selected,
  onClick,
  title,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      aria-label={title}
      title={title}
      className={clsx(
        "flex min-h-[34px] min-w-[34px] items-center justify-center rounded-md border",
        "transition-[border-color,background-color,color] duration-200",
        selected
          ? "border-accent/60 bg-accent/10 text-accent"
          : "border-border bg-background text-white/40 hover:border-border-strong hover:text-white/70"
      )}
    >
      {children}
    </button>
  );
}
