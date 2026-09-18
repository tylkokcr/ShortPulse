/**
 * Marks the document before first paint if this browser has a session.
 *
 * The problem it solves is a server-rendering one. `loading` starts true,
 * so RequireAuth returned `null` on the server and every page arrived as
 * an empty document — 44 characters of visible text, no headings, no link
 * to the privacy policy. Anything that does not execute 900KB of
 * JavaScript saw nothing at all, which is what Google's OAuth branding
 * check reported as a homepage that does not respond, and what made the
 * sitemap point crawlers at pages with no content in them.
 *
 * Rendering the landing page while loading fixes that and introduces the
 * flash RequireAuth's comment warned about: a signed-in user would see
 * the marketing page for the moment it takes to read the session back.
 * So this runs first, synchronously, in the document head — the same
 * trick the accent colour uses — and CSS hides the boot landing when the
 * attribute is set. The signed-in user never paints it; the crawler,
 * which has no storage and no attribute, gets the whole page.
 *
 * Supabase keys its token `sb-<project ref>-auth-token`, which is why
 * this matches a shape rather than a constant: the ref belongs to the
 * deployment, and hardcoding one would silently stop matching the day
 * somebody points the app at a different project.
 */
export const SESSION_BOOT_SCRIPT = `
try {
  for (var i = 0; i < localStorage.length; i++) {
    var k = localStorage.key(i);
    if (k && k.indexOf("sb-") === 0 && k.indexOf("-auth-token") > 0) {
      document.documentElement.setAttribute("data-session", "1");
      break;
    }
  }
} catch (e) {}
`.trim();
