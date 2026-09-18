import { Anton, Bangers, Permanent_Marker } from "next/font/google";

/**
 * The display faces, for the picker's previews only.
 *
 * Loaded through next/font rather than from Google's CDN because the CSP
 * is `font-src 'self'` — a <link> to fonts.gstatic.com is blocked with no
 * visible error, and the preview would quietly fall back to Arial while
 * claiming to show Anton. next/font fetches at build time and serves from
 * our own origin, which is the same reason the UI's own two families are
 * declared this way.
 *
 * These have to stay in step with app/assets/fonts on the backend: the
 * preview is only honest if the face here is the face libass burns in.
 */
export const anton = Anton({
  subsets: ["latin", "latin-ext"],
  weight: "400",
  display: "swap",
  variable: "--font-caption-anton",
});

export const bangers = Bangers({
  subsets: ["latin", "latin-ext"],
  weight: "400",
  display: "swap",
  variable: "--font-caption-bangers",
});

export const permanentMarker = Permanent_Marker({
  subsets: ["latin"],
  weight: "400",
  display: "swap",
  variable: "--font-caption-marker",
});

/** Applied to whatever wraps the previews, so the variables resolve. */
export const CAPTION_FONT_VARS = [
  anton.variable,
  bangers.variable,
  permanentMarker.variable,
].join(" ");
