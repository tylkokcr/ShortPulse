import { CAPTION_POSITIONS, CAPTION_SIZES, captionStyleFor, presetById } from "./captionStyles";
import type { AspectRatio, SubtitleStyle } from "./types";

/**
 * Named looks for a set of clips, picked in one tap.
 *
 * Setting a caption style, a position, a size and a frame on every upload
 * is four decisions to make the same way every time — which is what a
 * template is for. Opus Clip has these and they are worth borrowing; what
 * is not worth borrowing is the wall of toggles around them, so a
 * template here is one tile and nothing else.
 *
 * A template is a **shortcut, not a mode**. Picking one writes the
 * underlying fields and then gets out of the way: changing the caption
 * style afterwards is not "breaking" the template, it is just a different
 * style. Nothing stores which template was used, because nothing needs
 * to — the fields are the truth, exactly as they were before.
 *
 * Frontend-only, and deliberately so. The backend already has the idiom
 * for a server-owned catalogue (`art_styles.py`: frozen records, a tuple,
 * `by_id` with a safe default) and this does not need it: every field a
 * template sets is one the API already accepts individually, so a
 * template is a way of filling a form rather than a thing the server has
 * to know about.
 *
 * `captionStyleFor` composes the style, rather than this file doing it —
 * the same function the studio, the preview and the post-render editor
 * use. That is the whole reason it exists: there was a bug where the
 * upload path composed its own and threw the placement away.
 */
export interface ClipTemplate {
  id: string;
  name: string;
  description: string;
  /** Id from CAPTION_PRESETS — the look of the words. */
  captionPreset: string;
  /** Where they sit in the frame. */
  captionPosition: SubtitleStyle["position"];
  /** Pixel height at a 1080-wide frame, or null to keep the preset's own. */
  captionFontSize: number | null;
  /**
   * The frame the clips are cut to.
   *
   * Only an extraction reframes — the upload pipeline leaves the picture
   * as it was filmed — so a template with a non-vertical frame is refused
   * by the API unless clips were asked for. The panel dims the row rather
   * than letting the request fail.
   */
  aspectRatio: AspectRatio;
}

/**
 * Six, covering all three frames and all three positions between them.
 *
 * Chosen so the list demonstrates the range rather than offering six
 * variations of the same vertical bottom-third caption — the point of a
 * catalogue is that the options differ.
 */
export const CLIP_TEMPLATES: ClipTemplate[] = [
  {
    id: "podcast",
    name: "Podcast",
    description: "Plain captions, low in frame. Stays out of the way.",
    captionPreset: "classic",
    captionPosition: "bottom_third",
    captionFontSize: 84,
    aspectRatio: "9:16",
  },
  {
    id: "talking-head",
    name: "Talking head",
    description: "Words on a solid strip, readable over anything.",
    captionPreset: "block",
    captionPosition: "bottom_third",
    captionFontSize: 84,
    aspectRatio: "9:16",
  },
  {
    id: "hot-take",
    name: "Hot take",
    description: "Big and centred. Built to be read without sound.",
    captionPreset: "impact",
    captionPosition: "middle",
    captionFontSize: 100,
    aspectRatio: "9:16",
  },
  {
    id: "explainer",
    name: "Explainer",
    description: "Smaller type, longer lines. For talking through a point.",
    captionPreset: "clean",
    captionPosition: "bottom_third",
    captionFontSize: 72,
    aspectRatio: "9:16",
  },
  {
    id: "feed-square",
    name: "Feed square",
    description: "Square, captions high — where a feed crops the bottom.",
    captionPreset: "sticker",
    captionPosition: "top_third",
    captionFontSize: 84,
    aspectRatio: "1:1",
  },
  {
    id: "wide-cut",
    name: "Wide cut",
    description: "Keeps the original landscape frame. For YouTube.",
    captionPreset: "news",
    captionPosition: "bottom_third",
    captionFontSize: 72,
    aspectRatio: "16:9",
  },
];

export const DEFAULT_CLIP_TEMPLATE = CLIP_TEMPLATES[0];

/** Falls back rather than throwing, as `presetById` does: a stale id from
 *  an older client should give the default look, not a blank screen. */
export function templateById(id: string): ClipTemplate {
  return CLIP_TEMPLATES.find((template) => template.id === id) ?? DEFAULT_CLIP_TEMPLATE;
}

/** The style a template renders, composed the one way styles are composed. */
export function subtitlesFor(template: ClipTemplate): SubtitleStyle {
  return captionStyleFor({
    captionPreset: template.captionPreset,
    captionPosition: template.captionPosition,
    captionFontSize: template.captionFontSize,
  });
}

/**
 * Every template has to name things that exist.
 *
 * `presetById` falls back to the default, so a typo in `captionPreset`
 * would not throw — it would ship a template that silently renders as
 * Classic, which is the same class of failure the font comment in
 * `captionStyles.ts` warns about.
 *
 * Development only. There is no test runner in this package, so the
 * check runs at import and fails loudly on the first page that loads it;
 * running it in production too would mean a typo in a data file could
 * take down a page that was otherwise fine, which is a worse outcome than
 * the wrong caption style.
 */
if (process.env.NODE_ENV !== "production") {
  for (const template of CLIP_TEMPLATES) {
    if (presetById(template.captionPreset).id !== template.captionPreset) {
      throw new Error(
        `Clip template "${template.id}" names caption preset "${template.captionPreset}", which does not exist.`
      );
    }
    if (!(CAPTION_POSITIONS as readonly string[]).includes(template.captionPosition)) {
      throw new Error(
        `Clip template "${template.id}" names caption position "${template.captionPosition}", which does not exist.`
      );
    }
    if (
      template.captionFontSize !== null &&
      !CAPTION_SIZES.some((size) => size.px === template.captionFontSize)
    ) {
      throw new Error(
        `Clip template "${template.id}" sets caption size ${template.captionFontSize}, which is not one of the offered sizes.`
      );
    }
  }
}
