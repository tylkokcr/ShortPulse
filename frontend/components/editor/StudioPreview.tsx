"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";
import { useShortPulseStore } from "@/lib/store";
import { captionStyleFor, presetById } from "@/lib/captionStyles";
import type { AspectRatio, LanguageCode } from "@/lib/types";

/**
 * A live composite of the choices made so far.
 *
 * Nothing here is decorative: the frame takes the selected aspect ratio's
 * real proportions, the backdrop is the actual sample frame for the chosen
 * art style, and the caption is drawn from the same preset the renderer
 * burns in — word count per line, casing, highlight colour and vertical
 * placement included. Changing a control changes this, which is the point:
 * a form tells you what you picked, a preview shows you.
 *
 * It is a preview, not the render. `PREVIEW_CAPTION` stands in for a line
 * the script hasn't written yet.
 */
const ASPECT_CLASS: Record<AspectRatio, string> = {
  "9:16": "aspect-[9/16] max-w-[210px]",
  "1:1": "aspect-square max-w-[280px]",
  "16:9": "aspect-video max-w-[320px]",
};

/**
 * The stand-in caption, in the language that will actually be rendered.
 *
 * Every other control on the left shows up on the right; language was the
 * one that didn't, so picking Türkçe or Deutsch left an English line
 * sitting under the frame — the preview quietly contradicting the setting
 * above it. The lines all say the same thing, because what is being
 * previewed is the caption's *shape*: where it breaks, whether it is
 * uppercase, which word is lit. A translation that runs longer or shorter
 * than the English is the point rather than a problem — that is what the
 * line will do in the render too.
 *
 * Keyed by LanguageCode rather than by LANGUAGE_OPTIONS, so a language
 * added to the type without a line here fails the build instead of
 * silently falling back to English. "ja" is in the type but not offered
 * yet: Piper ships no Japanese voice.
 */
const PREVIEW_CAPTION: Record<LanguageCode, string[]> = {
  en: ["your", "words", "land", "on", "the", "beat"],
  tr: ["sözlerin", "ritme", "tam", "oturur"],
  es: ["tus", "palabras", "caen", "al", "ritmo"],
  fr: ["tes", "mots", "tombent", "sur", "le", "rythme"],
  de: ["deine", "Worte", "treffen", "den", "Beat"],
  pt: ["suas", "palavras", "caem", "no", "ritmo"],
  ja: ["言葉が", "ビートに", "乗る"],
  ar: ["كلماتك", "تنزل", "على", "الإيقاع"],
  ru: ["твои", "слова", "попадают", "в", "ритм"],
  it: ["le", "tue", "parole", "cadono", "a", "tempo"],
};

/**
 * Arabic is the one right-to-left language on offer. The words are laid
 * out as individual spans here, so without this the browser renders them
 * left to right and the line reads backwards to anyone who can read it.
 */
const RTL_LANGUAGES: ReadonlySet<LanguageCode> = new Set<LanguageCode>(["ar"]);

export function StudioPreview() {
  const t = useTranslations("studio.preview");
  const { draft } = useShortPulseStore();
  const preset = presetById(draft.captionPreset);
  // The resolved style, not the preset's — the same function the submit
  // uses, so the preview cannot promise a placement the render ignores.
  const style = captionStyleFor(draft);
  const perLine = style.max_words_per_line;
  const caption = PREVIEW_CAPTION[draft.language];

  const lines: string[][] = [];
  for (let i = 0; i < caption.length; i += perLine) {
    lines.push(caption.slice(i, i + perLine));
  }

  const placement =
    style.position === "middle"
      ? "items-center"
      : style.position === "top_third"
        ? "items-start"
        : "items-end";

  // The preview box is a couple of hundred pixels tall, so the font size
  // cannot be used directly — it is carried across as a ratio against the
  // preset's own size, which is what the tuned base below assumes.
  const sizeRatio = style.font_size / preset.style.font_size;

  // Stock footage has no art style, so there's no representative frame to
  // show — a style sample there would promise a look it won't deliver.
  const backdrop =
    draft.visualMode === "stock_media" ? null : `/art-styles/${draft.artStyle}.jpg`;

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className={clsx(
          "relative w-full overflow-hidden rounded-md border border-border-strong bg-neutral-900 shadow-2xl shadow-black/50 transition-all duration-300",
          ASPECT_CLASS[draft.aspectRatio],
          placement,
          "flex justify-center"
        )}
      >
        {backdrop ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={backdrop}
            src={backdrop}
            alt=""
            aria-hidden
            className="absolute inset-0 h-full w-full object-cover animate-fade-in"
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-neutral-700 via-neutral-800 to-neutral-900" />
        )}

        {/* Keeps captions readable over a bright frame, exactly as the
            burned-in outline does in the real render. */}
        <div className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-black/70 to-transparent" />

        <p
          // Not decoration: CSS `text-transform: uppercase` follows the
          // element's language, and Turkish "i" uppercases to "İ" rather
          // than "I". Without this the preview shows RITME where the
          // render now writes RİTME (see subtitle_engine._uppercase) —
          // the preview would be lying about the one thing it exists to
          // show.
          lang={draft.language}
          dir={RTL_LANGUAGES.has(draft.language) ? "rtl" : "ltr"}
          className={clsx(
            "relative z-10 px-3 text-center font-extrabold leading-tight",
            style.uppercase ? "uppercase" : "normal-case",
            // Padding follows the placement: a top caption pinned with
            // bottom padding sits against the edge of the frame, which is
            // the one thing the top option exists to avoid.
            style.position === "top_third" ? "pt-4" : style.position === "middle" ? "" : "pb-4"
          )}
          style={{
            fontSize: `${(draft.aspectRatio === "16:9" ? 11 : 12) * sizeRatio}px`,
            textShadow: `0 0 ${style.outline_width}px #000, 0 1px 3px #000`,
          }}
        >
          {lines.map((line, li) => (
            <span key={li} className="block">
              {line.map((word, wi) => (
                <span
                  key={`${li}-${word}`}
                  style={{ color: wi === (li === 0 ? 1 : 0) ? preset.previewHighlight : "#fff" }}
                >
                  {word}{" "}
                </span>
              ))}
            </span>
          ))}
        </p>
      </div>

      <p className="text-center font-mono text-[10px] leading-relaxed text-white/30">
        {t("note")}
      </p>
    </div>
  );
}
