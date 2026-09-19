import type { MetadataRoute } from "next";
import { routing } from "@/i18n/routing";
import { siteUrl } from "@/lib/siteUrl";

const PRIVATE = ["/library", "/connections", "/credits", "/project/", "/reset-password"];

/**
 * What a crawler may read.
 *
 * Everything behind sign-in is disallowed — not to hide it, since a
 * crawler gets the landing page there anyway, but because those URLs are
 * per-user and there is nothing at them worth a crawl budget. `/api` is
 * disallowed for the same reason plus one: the media routes carry signed
 * tokens in the query string, and a crawler following one would put a
 * URL that grants access to a finished video into somebody's index.
 */
export default function robots(): MetadataRoute.Robots {
  const base = siteUrl();

  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Each private path in every language. A bare "/library" would
      // leave /tr/library open, and those URLs are per-user with the
      // landing page behind them for anyone signed out — four more
      // addresses showing the same marketing copy is exactly the
      // duplicate-content shape the sitemap is arranged to avoid.
      disallow: PRIVATE.flatMap((path) =>
        routing.locales.map((locale) =>
          locale === routing.defaultLocale ? path : `/${locale}${path}`
        )
      ).concat("/api/"),
    },
    // Omitted rather than guessed on an install that has no public
    // address: a sitemap line pointing at localhost is worse than none.
    ...(base ? { sitemap: `${base}/sitemap.xml` } : {}),
  };
}
