import { defineRouting } from "next-intl/routing";

/**
 * Four languages, English unprefixed.
 *
 * `localePrefix: "as-needed"` is not a style choice. https://shortpulse.app
 * and /privacy and /terms are registered in the Google OAuth consent
 * screen and were indexed days ago; moving English to /en would break
 * both. English keeps the bare paths and the other three get prefixes.
 *
 * Polish and German are here for the market the business is actually
 * registered in and the one next to it; Turkish because the author's own
 * circle is the nearest audience there is. Nothing about this list
 * relates to LANGUAGE_OPTIONS in lib/types.ts — that is the language a
 * *video* is spoken in, and the two must not be conflated.
 */
export const routing = defineRouting({
  locales: ["en", "tr", "pl", "de"],
  defaultLocale: "en",
  localePrefix: "as-needed",
});

export type Locale = (typeof routing.locales)[number];

/** Shown in the switcher. Autonyms, because a language name is most
 *  useful to the person who reads that language. */
export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  tr: "Türkçe",
  pl: "Polski",
  de: "Deutsch",
};
