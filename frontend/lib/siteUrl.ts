/**
 * Where this deployment lives, for the files that have to say it out loud.
 *
 * robots.txt and sitemap.xml are generated on the server at build time,
 * so `window.location` is not available and the domain has to come from
 * configuration. Derived from NEXT_PUBLIC_WS_ORIGIN rather than a setting
 * of its own: both would come from SITE_ADDRESS in the compose file, and
 * a second place to write the domain is a second place for it to be
 * wrong — the same reason CORS_ORIGINS is derived rather than configured.
 *
 * Empty on a self-hosted install with no origin configured, which is the
 * honest answer: a machine reachable only on localhost has no canonical
 * address, and inventing one would publish a sitemap full of links that
 * resolve nowhere.
 */
export function siteUrl(): string {
  const ws = process.env.NEXT_PUBLIC_WS_ORIGIN;
  if (!ws) return "";
  return ws.replace(/^ws:/, "http:").replace(/^wss:/, "https:").replace(/\/$/, "");
}
