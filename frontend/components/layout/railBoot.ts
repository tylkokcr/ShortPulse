/**
 * Marks the rail collapsed before first paint.
 *
 * Same shape and the same reason as the accent: the choice lives in
 * localStorage, the server cannot know it, and applying it after React
 * mounts means every navigation opens with the rail at the wrong width
 * and snaps. An attribute on <html> and a CSS rule is the only version
 * of this that never flashes.
 *
 * Kept out of any "use client" module deliberately — a client module
 * exports references to the server, not values, and interpolating one
 * into the head script silently produced a syntax error the last time.
 * See accentBoot for the full story.
 */
export const RAIL_STORAGE_KEY = "shortpulse.rail";

export const RAIL_BOOT_SCRIPT = `
try {
  if (localStorage.getItem(${JSON.stringify(RAIL_STORAGE_KEY)}) === "collapsed")
    document.documentElement.setAttribute("data-rail", "collapsed");
} catch (e) {}
`.trim();
