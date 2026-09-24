import type { SubtitleStyle } from "./types";

/**
 * Named caption presets.
 *
 * These are not decoration: every field maps onto a real `SubtitleStyle`
 * the backend burns into the video with libass, so what the picker
 * promises is what the .ass file gets.
 *
 * Colours are ASS `&HAABBGGRR` — byte-reversed from CSS hex, which is why
 * each one carries the CSS equivalent alongside it for the preview swatch.
 *
 * `font_family` may only name a font this repository actually ships, in
 * app/assets/fonts. libass silently substitutes a face it cannot find, so
 * a preset naming anything else would look right here and wrong in the
 * output — a failure nobody catches until they watch the video.
 *
 * The same applies per language: a font covers the alphabets it covers,
 * and the backend swaps in one that can draw the project's language when
 * the chosen face cannot. `notCovered` below is that fact made visible, so
 * the picker can say so before the render rather than after.
 */
export interface CaptionPreset {
  id: string;
  name: string;
  description: string;
  /** CSS colour matching `style.highlight_color`, for the live preview. */
  previewHighlight: string;
  /** CSS colour matching `style.outline_color`, which on a boxed preset is
   *  the strip behind the words rather than a stroke around them. */
  previewBox?: string;
  /** CSS colour matching `style.primary_color`. Only worth stating where
   *  it is not white — a dark box wants white words and a white one does
   *  not, and the preview has to make the same choice the renderer does. */
  previewText?: string;
  /** Languages this preset's font cannot draw, which the renderer will
   *  substitute Montserrat (or Noto Sans Arabic) for. Mirrors
   *  `subtitle_engine.FONT_COVERAGE`; keep the two in step. */
  notCovered?: string[];
  /** CSS stack for the preview, matching the bundled face. */
  previewFont?: string;
  style: SubtitleStyle;
}

/** Languages none of the display faces can draw — they are Latin-only. */
const NON_LATIN = ["ar", "ru"];

const BASE: SubtitleStyle = {
  font_family: "Montserrat",
  font_size: 84,
  primary_color: "&H00FFFFFF",
  highlight_color: "&H0000D7FF",
  outline_color: "&H00000000",
  outline_width: 4,
  position: "bottom_third",
  max_words_per_line: 4,
  uppercase: true,
};

export const CAPTION_PRESETS: CaptionPreset[] = [
  {
    id: "classic",
    name: "Classic",
    description: "White with a gold active word. The default.",
    previewHighlight: "#FFD700",
    style: { ...BASE },
  },
  {
    id: "punch",
    name: "Punch",
    description: "Bigger, thicker, three words at a time.",
    previewHighlight: "#00FF00",
    style: {
      ...BASE,
      font_size: 96,
      highlight_color: "&H0000FF00",
      outline_width: 6,
      max_words_per_line: 3,
    },
  },
  {
    id: "clean",
    name: "Clean",
    description: "Sentence case, lighter outline, longer lines.",
    previewHighlight: "#2DD4BF",
    style: {
      ...BASE,
      font_size: 72,
      highlight_color: "&H00BFD42D",
      outline_width: 3,
      max_words_per_line: 5,
      uppercase: false,
    },
  },
  {
    id: "spotlight",
    name: "Spotlight",
    description: "Centred on screen — good over busy footage.",
    previewHighlight: "#7C5CFF",
    style: {
      ...BASE,
      font_size: 88,
      highlight_color: "&H00FF5C7C",
      outline_width: 5,
      position: "middle",
      max_words_per_line: 3,
    },
  },

  // Boxed. The active word's *block* changes colour rather than its
  // letters, which is why these read differently from anything above
  // however the colours are set — and why they hold up over pale or busy
  // footage, where an outline is the first thing to disappear.
  {
    id: "block",
    name: "Block",
    description: "White on a black strip, active word in orange.",
    previewHighlight: "#FF4500",
    previewBox: "#000000",
    style: {
      ...BASE,
      box: true,
      outline_color: "&H00000000",
      highlight_color: "&H000045FF",
      outline_width: 8,
      max_words_per_line: 3,
    },
  },
  {
    id: "tape",
    name: "Tape",
    description: "A red band with a yellow active word. Loud on purpose.",
    previewHighlight: "#FFFF00",
    previewBox: "#FF1428",
    style: {
      ...BASE,
      box: true,
      outline_color: "&H002814FF",
      highlight_color: "&H0000FFFF",
      outline_width: 10,
      max_words_per_line: 3,
      letter_spacing: 1,
    },
  },
  {
    id: "news",
    name: "News",
    description: "Sentence case in a dark band, centred. Quiet and legible.",
    previewHighlight: "#7DD3FC",
    previewBox: "#0F172A",
    style: {
      ...BASE,
      box: true,
      font_size: 68,
      outline_color: "&H001E120F",
      highlight_color: "&H00FCD37D",
      outline_width: 8,
      max_words_per_line: 5,
      uppercase: false,
      position: "middle",
    },
  },
  {
    id: "sticker",
    name: "Sticker",
    description: "Big words on a white block, high on the frame.",
    previewHighlight: "#FF2D95",
    previewBox: "#FFFFFF",
    previewText: "#141414",
    style: {
      ...BASE,
      box: true,
      font_size: 92,
      primary_color: "&H00141414",
      outline_color: "&H00FFFFFF",
      highlight_color: "&H00952DFF",
      outline_width: 10,
      max_words_per_line: 2,
      position: "top_third",
    },
  },

  // The three that change the letterforms rather than their colour. Each
  // names a face bundled in app/assets/fonts; none of them can draw
  // Cyrillic or Arabic, which is what `notCovered` is for.
  {
    id: "impact",
    name: "Impact",
    description: "Tall condensed caps. Fits more per line and shouts.",
    previewHighlight: "#FACC15",
    previewFont: "var(--font-caption-anton), 'Arial Narrow', sans-serif",
    notCovered: NON_LATIN,
    style: {
      ...BASE,
      font_family: "Anton",
      font_size: 104,
      highlight_color: "&H0015CCFA",
      outline_width: 5,
      max_words_per_line: 3,
    },
  },
  {
    id: "comic",
    name: "Comic",
    description: "Hand-lettered, on a yellow block. Playful.",
    previewHighlight: "#F43F5E",
    previewBox: "#FACC15",
    previewText: "#141414",
    previewFont: "var(--font-caption-bangers), 'Comic Sans MS', cursive",
    notCovered: NON_LATIN,
    style: {
      ...BASE,
      font_family: "Bangers",
      box: true,
      font_size: 100,
      primary_color: "&H00141414",
      outline_color: "&H0015CCFA",
      highlight_color: "&H005E3FF4",
      outline_width: 10,
      max_words_per_line: 3,
    },
  },
  {
    id: "marker",
    name: "Marker",
    description: "Felt-tip handwriting. No Turkish — it has no ğ, ş or ı.",
    previewHighlight: "#34D399",
    previewFont: "var(--font-caption-marker), cursive",
    notCovered: [...NON_LATIN, "tr"],
    style: {
      ...BASE,
      font_family: "Permanent Marker",
      font_size: 92,
      highlight_color: "&H0099D334",
      outline_width: 5,
      max_words_per_line: 3,
      uppercase: false,
    },
  },
];

export const DEFAULT_CAPTION_PRESET = CAPTION_PRESETS[0];

export function presetById(id: string): CaptionPreset {
  return CAPTION_PRESETS.find((preset) => preset.id === id) ?? DEFAULT_CAPTION_PRESET;
}

/** The three places captions are allowed to sit.
 *
 *  Three rather than a free position: `subtitle_engine` maps each one to
 *  an ASS alignment and a vertical margin, and a percentage would have to
 *  be plumbed through that mapping on the backend before it meant
 *  anything here. Three is also what the frame can honestly offer — a
 *  caption anywhere but a third is either over the subject's face or off
 *  the safe area every platform crops into.
 */
export const CAPTION_POSITIONS = ["top_third", "middle", "bottom_third"] as const;

/** Three sizes, as real pixel heights at a 1080-wide frame.
 *
 *  Absolute rather than a multiplier on the preset, because the same
 *  control edits a finished project's stored style — where there is no
 *  preset left to multiply. A multiplier would also drift: apply "large"
 *  twice across two visits and the second one scales the first one's
 *  result.
 *
 *  The range is narrow on purpose. libass wraps a line that no longer
 *  fits rather than overflowing the frame, so the failure past `large` is
 *  a four-word caption silently becoming two lines and covering more
 *  picture than anyone asked for.
 */
export const CAPTION_SIZES = [
  { id: "small", px: 72 },
  { id: "normal", px: 84 },
  { id: "large", px: 100 },
] as const;

/** Which step a stored size is nearest to.
 *
 *  Nearest rather than exact: a preset is free to pick any size and most
 *  do not land on one of these three, so the control has to be able to
 *  show where an arbitrary value sits.
 */
export function sizeIdFor(px: number): string {
  return CAPTION_SIZES.reduce((best, step) =>
    Math.abs(step.px - px) < Math.abs(best.px - px) ? step : best
  ).id;
}

/** The preset's look, with the viewer's own placement on top.
 *
 *  One function so the studio, the live preview and the post-render
 *  editor cannot disagree about what the render will be — they were three
 *  places to forget the same two fields.
 */
export function captionStyleFor(draft: {
  captionPreset: string;
  captionPosition: SubtitleStyle["position"];
  /** null keeps whatever size the preset chose, which is what an
   *  untouched control means — not "84". */
  captionFontSize: number | null;
}): SubtitleStyle {
  const base = presetById(draft.captionPreset).style;
  return {
    ...base,
    position: draft.captionPosition,
    font_size: draft.captionFontSize ?? base.font_size,
  };
}
