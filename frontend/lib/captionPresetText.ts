"use client";

import { useTranslations } from "next-intl";
import type { CaptionPreset } from "./captionStyles";

/**
 * A caption preset's name and description in the reader's language.
 *
 * The presets live in captionStyles.ts with English words beside the
 * numbers the renderer reads; the Turkish landing page listed them as
 * "White with a gold active word". Translated here by id, with the file's
 * own words as the fallback for a preset added without them.
 */
export function useCaptionPresetText() {
  const t = useTranslations("captionPresetCatalog");
  return (preset: Pick<CaptionPreset, "id" | "name" | "description">) => {
    const known = t.has(`${preset.id}.name`);
    return {
      name: known ? t(`${preset.id}.name`) : preset.name,
      description: known ? t(`${preset.id}.description`) : preset.description,
    };
  };
}
