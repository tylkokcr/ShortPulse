"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";

/**
 * Bleep the strong language, and mask it on screen.
 *
 * Off by default and stated plainly, because it silences part of
 * somebody's audio — a thing to do when asked, not by default. The hint
 * says what it actually does rather than promising safety: the list is
 * finite and spelling is not, so this is a convenience for a video that
 * has to pass an advertiser rule, not a guarantee to anyone.
 *
 * Controlled rather than reading the store, because the same control
 * appears in the upload panel, where the choice belongs to that form
 * rather than to the generate draft.
 */
export function CensorToggle({
  checked,
  onChange,
  className,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  className?: string;
}) {
  const t = useTranslations("studio.censor");

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
