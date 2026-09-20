/**
 * Applies the stored accent colour before first paint.
 *
 * Without it the page renders in ember and swaps once React mounts — a
 * colour flash on every full load, which is worse than not offering the
 * choice at all. Kept as a string so it can be inlined in the document
 * head; it must stay small, synchronous and unable to throw, because it
 * runs before anything else on the page.
 *
 * It lives in its own module, away from the switcher that uses the same
 * key, for one reason that cost an afternoon: a `"use client"` file does
 * not export values to the server. It exports *references*. Interpolating
 * one into a template literal on the server does not read the string —
 * it stringifies the proxy, and what reached the browser was the tail of
 * an error stub reading "BOOT_SCRIPT is on the client", followed by
 * the rest of the head script. No build error, no console error, just an
 * accent that silently never applied. The same rule keeps
 * SESSION_BOOT_SCRIPT in its own file next to AuthProvider.
 */
export const ACCENT_STORAGE_KEY = "shortpulse.accent";

export const ACCENT_BOOT_SCRIPT = `
try {
  var a = localStorage.getItem(${JSON.stringify(ACCENT_STORAGE_KEY)});
  if (a && a !== "ember") document.documentElement.setAttribute("data-accent", a);
} catch (e) {}
`.trim();
