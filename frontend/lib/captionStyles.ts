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
 * `font_family` is deliberately the same everywhere. libass silently falls
 * back to a default face when a font isn't installed on the render
 * machine, so a preset that switched fonts would look correct here and
 * wrong in the output — a failure nobody would catch until they watched
 * the finished video.
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
  style: SubtitleStyle;
}

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
];

export const DEFAULT_CAPTION_PRESET = CAPTION_PRESETS[0];

export function presetById(id: string): CaptionPreset {
  return CAPTION_PRESETS.find((preset) => preset.id === id) ?? DEFAULT_CAPTION_PRESET;
}
