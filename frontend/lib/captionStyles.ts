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
];

export const DEFAULT_CAPTION_PRESET = CAPTION_PRESETS[0];

export function presetById(id: string): CaptionPreset {
  return CAPTION_PRESETS.find((preset) => preset.id === id) ?? DEFAULT_CAPTION_PRESET;
}
