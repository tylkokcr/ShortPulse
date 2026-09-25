"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";

/**
 * A quick zoom that settles as each scene starts.
 *
 * On by default, which is the unusual half: it changes what every
 * generated video looks like. That is deliberate — a still frame held
 * for the length of a spoken line reads as a slideshow, and that is what
 * this product's output was.
 *
 * Only stock and AI-video clips are touched. AI stills already get Ken
 * Burns, and a punch on top of a drift is two moves fighting.
 */
export function PunchToggle({
  checked,
  onChange,
  className,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  className?: string;
}) {
  const t = useTranslations("studio.punch");

  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-white/80">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          className="h-4 w-4 rounded border-border accent-accent"
        />
        {t("toggle")}
      </label>
      <p className="text-[11px] leading-relaxed text-white/30">{t("hint")}</p>
    </div>
  );
}
