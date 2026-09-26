import type { LanguageCode } from "@/lib/types";

/**
 * The example renders, and who to credit for them.
 *
 * Shared because two places show these clips now: the marketing strip and
 * the studio's "start from an example" row. The Pexels credit below is a
 * condition of using the footage, so it travels with the list rather than
 * living in whichever component happened to be written first — a second
 * copy is how one of them silently stops matching the videos on screen.
 */

/**
 * Real renders, not mockups.
 *
 * Every clip here came out of this pipeline and lives in
 * `frontend/public/examples` (transcoded down from the original 1080x1920
 * masters for page weight — same frames, same audio, lower bitrate).
 * Durations and scene counts are read off the rendered projects rather
 * than chosen to look good.
 *
 * Sixteen are `stock_media` and one is `fast_hybrid`, marked on the card.
 * Both are here on purpose: for most of this page's life every example was
 * stock footage, which meant a visitor judged the three-credit mode by the
 * one-credit one and the paid mode looked like whatever they imagined.
 *
 * AI stills were tried here first, years of model progress ago, and were
 * not honest to show — local diffusion at this size put a doubled nose on
 * this very sleep script. That stopped being true when fast_hybrid moved
 * to RealVisXL over an API: on a side-by-side of the same topic the
 * generated frames held their faces and kept one subject across every
 * scene, while the stock cut matched a caregiving clip to a line about
 * attraction. The eleventh entry is that render.
 *
 * The .mp4 files are gitignored — see the README in public/examples for
 * why, and for the step that gets them onto the server, which a git pull
 * cannot do for you.
 */
export interface Example {
  slug: string;
  title: string;
  /** What the language is called in itself, for display. Deliberately not
   *  run through the translation catalogue — see the note in Landing. */
  language: string;
  /** The same language as a code the draft can carry. The strip never
   *  needed it; loading an example into the studio does. Typed as the
   *  draft's own union so a clip in a language the pipeline cannot speak
   *  fails the build rather than the render. */
  languageCode: LanguageCode;
  seconds: number;
  scenes: number;
  /** Marked only on the AI-stills entries. Absent means stock footage,
   *  which is what most of these are and what the credit line below
   *  covers — a generated clip has no videographer to name. */
  aiStills?: boolean;
  /**
   * Rendered 1:1 rather than 9:16.
   *
   * The studio's strip sits above the form on a working screen, and four
   * vertical clips made it as tall as the form itself — a row of letterbox
   * slivers you scroll past to reach the topic field. Square renders are a
   * third of the height and the frames read at that size.
   *
   * The marquee on the landing page keeps the vertical ones. That page is
   * selling what the product makes, and what it makes by default is
   * 9:16 — a square showcase would quietly claim otherwise.
   */
  square?: boolean;
}

export const EXAMPLES: Example[] = [
  { slug: "honey", languageCode: "en", title: "Why honey never spoils", language: "English", seconds: 24, scenes: 5 },
  { slug: "dreams-tr", languageCode: "tr", title: "Neden gece rüya görürüz?", language: "Türkçe", seconds: 18, scenes: 5 },
  { slug: "moon-fr", languageCode: "fr", title: "Pourquoi la lune change-t-elle de forme ?", language: "Français", seconds: 25, scenes: 6 },
  { slug: "ocean", languageCode: "en", title: "Why the ocean is salty", language: "English", seconds: 19, scenes: 5 },
  { slug: "leaves-de", languageCode: "de", title: "Warum färben sich Blätter im Herbst?", language: "Deutsch", seconds: 20, scenes: 5 },
  { slug: "sky-es", languageCode: "es", title: "¿Por qué el cielo es azul?", language: "Español", seconds: 17, scenes: 5 },
  { slug: "cats-ar", languageCode: "ar", title: "لماذا تخاف القطط من الماء؟", language: "العربية", seconds: 21, scenes: 5 },
  { slug: "lightning", languageCode: "en", title: "How lightning actually forms", language: "English", seconds: 23, scenes: 5 },
  { slug: "yawn-pt", languageCode: "pt", title: "Por que bocejamos?", language: "Português", seconds: 26, scenes: 5 },
  { slug: "coffee", languageCode: "en", title: "Why coffee wakes you up", language: "English", seconds: 24, scenes: 5 },
  { slug: "night-ru", languageCode: "ru", title: "Почему небо ночью тёмное?", language: "Русский", seconds: 11, scenes: 5 },
  { slug: "cats-tr", languageCode: "tr", title: "Kediler neden kutuları sever?", language: "Türkçe", seconds: 22, scenes: 5 },
  { slug: "espresso-it", languageCode: "it", title: "Perché il caffè ci sveglia?", language: "Italiano", seconds: 16, scenes: 5 },
  { slug: "volcano", languageCode: "en", title: "Why volcanoes erupt", language: "English", seconds: 24, scenes: 5 },
  { slug: "goosebumps", languageCode: "en", title: "Why we get goosebumps", language: "English", seconds: 18, scenes: 5 },
  { slug: "sleep", languageCode: "en", title: "A simple trick for better sleep", language: "English", seconds: 19, scenes: 5 },
  // The one AI-stills entry, and the reason the comment above no longer
  // applies. Numbers read off the render: 8 scenes, 23.6s, photoreal.
  {
    slug: "quiet-observers",
    languageCode: "en",
    title: "Why quiet people read the room",
    language: "English",
    seconds: 24,
    scenes: 8,
    aiStills: true,
  },
  // Square renders, for the studio's own strip.
  //
  // Same pipeline, same stock mode, `aspect_ratio: "1:1"` — which is also
  // the first time that setting has been exercised end to end, and it
  // came back 1080x1080. Kept as separate entries rather than replacing
  // the vertical ones, because the landing marquee is selling the format
  // the product makes by default and these are not it.
  { slug: "ocean-sq", languageCode: "en", title: "Why the ocean is salty", language: "English", seconds: 21, scenes: 5, square: true },
  // The AI-stills one, square. Same render as its vertical twin in kind:
  // fast_hybrid over Replicate, photoreal, so the strip still shows what
  // the three-credit mode produces rather than judging it by the
  // one-credit one.
  { slug: "quiet-sq", languageCode: "en", title: "Why quiet people read the room", language: "English", seconds: 20, scenes: 5, square: true, aiStills: true },
  { slug: "dreams-sq", languageCode: "tr", title: "Neden gece rüya görürüz?", language: "Türkçe", seconds: 21, scenes: 5, square: true },
  { slug: "cats-sq", languageCode: "ar", title: "لماذا تخاف القطط من الماء؟", language: "العربية", seconds: 20, scenes: 4, square: true },
];

/**
 * Pexels' API terms require a visible link back to Pexels and credit to
 * the videographer. The pipeline records who shot each clip at fetch time;
 * this is that list, deduplicated across all sixteen stock-footage videos.
 */
export const FOOTAGE_CREDITS = [
  "Aaron Burden", "Abdullah | 4K", "Adventure Studio", "Aleks Magnusson", "Alexey Chudin",
  "Ambareesh Sridhar Photography", "Ana Sandu", "Andre Moura", "Andres Perez",
  "Angela Roma", "Anna Pou", "Anna Shvets", "Artem Podrez", "aslı aydoğdu", "Bahri Gün",
  "Barbara Olsen", "Bav Vadgama", "Ben Prater", "Canan İldeniz", "cottonbro studio",
  "Darina Belonogova", "Deti riyanti", "Ebahir", "Emrah", "Eyüp Can", "Grigoriy Bunkov",
  "Hale Ş", "Hashim Suhimi", "Iceberg San", "Ilya Lyzhin", "John Diez", "Joolsmagools ®️",
  "Juan Camilo Trujillo  Botero 🇨🇴📸", "JUN HO LEE", "K", "Kakada Chuon", "Kevin  Malik",
  "khezez | خزاز", "Koushalya Karthikeyan", "LauraB", "Lentes  Bella", "Luis Quintero",
  "Marina Leonova", "Masha Glazova", "Matthias Groeneveld", "Max Medyk", "Michael Burrows",
  "Mikhail Nilov", "Mizuno K", "Muhtelifane", "Nadezhda Moryak", "Nicola Narracci",
  "Nikita Ryumshin", "Nisasu", "Pachon in Motion", "Pavel Danilyuk", "Photoviewx",
  "Physical  Pixel", "RDNE Stock project", "ROMAN ODINTSOV", "Ron Lach", "Sema",
  "Shan Ali", "Stefanie Jockschat", "Thuan Pham", "Tima Miroshnichenko", "Timothy Fuller",
  "Timur Weber", "Toni.063371 -  Antonio Sáez", "Yuliya Duzhaya", "Şahin Doğdu",
];
