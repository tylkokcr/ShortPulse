"use client";

import { useTranslations } from "next-intl";
import type { ArtStyle } from "./types";

/**
 * An art style's name and description in the reader's language.
 *
 * The catalogue comes from the server (`art_styles.py`), in English,
 * because the same records drive the image prompts and those stay
 * English. What a person reads is translated here, keyed by the style's
 * id; a style the catalogue below does not know yet falls back to the
 * server's own words rather than to a missing-key path.
 */
export function useArtStyleText() {
  const t = useTranslations("artStyleCatalog");
  return (style: Pick<ArtStyle, "id" | "name" | "description">) => {
    const known = t.has(`${style.id}.name`);
    return {
      name: known ? t(`${style.id}.name`) : style.name,
      description: known ? t(`${style.id}.description`) : style.description,
    };
  };
}
