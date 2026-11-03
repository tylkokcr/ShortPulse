"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";

/**
 * The info graphics of a "what if?" video — a counter, the list that grows
 * with each consequence, stamps on the big moments — and their sound
 * effects. On by default for that format, which writes the data for them;
 * the script still carries it when this is off, so turning it back on and
 * editing the video brings them back.
 */
export function GraphicsToggle({
  checked,
  onChange,
  className,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  className?: string;
}) {
  const t = useTranslations("studio.graphics");

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
