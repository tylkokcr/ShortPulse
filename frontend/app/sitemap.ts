import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/siteUrl";

/**
 * The four pages a stranger can actually read.
 *
 * Everything else in the app is behind sign-in and renders the landing
 * page to anyone else, so listing it would offer Google four more URLs
 * that all resolve to the same thing — which is how a small site teaches
 * a crawler that its pages are duplicates.
 *
 * /login is here because it is the page a search for the product's name
 * plus "sign in" should land on, and it is genuinely public.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();
  if (!base) return [];

  return [
    { url: base, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/login`, changeFrequency: "yearly", priority: 0.5 },
    { url: `${base}/privacy`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${base}/terms`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
