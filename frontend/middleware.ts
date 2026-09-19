import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  /**
   * Everything except the things that must keep their exact path.
   *
   * `/api` is proxied to the backend by next.config.mjs and must not be
   * rewritten — a locale prefix there would send the browser to a route
   * the API has never heard of. robots.txt, sitemap.xml and icon.svg are
   * addresses other systems hold: Google reads the first two, and the
   * third is referenced from the OAuth consent screen's branding.
   */
  matcher: ["/((?!api|_next|robots\\.txt|sitemap\\.xml|icon\\.svg|examples|.*\\..*).*)"],
};
