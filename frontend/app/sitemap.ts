import type { MetadataRoute } from "next";
import { routing } from "@/i18n/routing";
import { siteUrl } from "@/lib/siteUrl";

/**
 * The pages a stranger can read, in every language they exist in.
 *
 * Everything else in the app is behind sign-in and renders the landing
 * page to anyone else, so listing it would offer Google more URLs that
 * all resolve to the same thing — which is how a small site teaches a
 * crawler that its pages are duplicates.
 *
 * /login is here because it is the page a search for the product's name
 * plus "sign in" should land on, and it is genuinely public.
 *
 * Each entry carries `alternates.languages`, which is what tells Google
 * that /tr is the Turkish version of / rather than a separate thin page
 * saying much the same thing. Without it four translations of one site
 * compete with each other.
 *
 * Note /privacy and /terms are listed once, unprefixed: they are only
 * published in English, deliberately — a machine translation of a
 * privacy policy can misstate an obligation.
 */
const TRANSLATED = [
  { path: "", changeFrequency: "weekly" as const, priority: 1 },
  { path: "/login", changeFrequency: "yearly" as const, priority: 0.5 },
];

const ENGLISH_ONLY = [
  { path: "/privacy", changeFrequency: "yearly" as const, priority: 0.3 },
  { path: "/terms", changeFrequency: "yearly" as const, priority: 0.3 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();
  if (!base) return [];

  const localised = (locale: string, path: string) =>
    locale === routing.defaultLocale ? `${base}${path}` || base : `${base}/${locale}${path}`;

  const translated = routing.locales.flatMap((locale) =>
    TRANSLATED.map(({ path, changeFrequency, priority }) => ({
      url: localised(locale, path),
      changeFrequency,
      priority,
      alternates: {
        languages: Object.fromEntries(
          routing.locales.map((l) => [l, localised(l, path)])
        ),
      },
    }))
  );

  return [
    ...translated,
    ...ENGLISH_ONLY.map(({ path, changeFrequency, priority }) => ({
      url: `${base}${path}`,
      changeFrequency,
      priority,
    })),
  ];
}
