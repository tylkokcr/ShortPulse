"use client";

import { useState } from "react";
import clsx from "clsx";
import { CAPTION_PRESETS } from "@/lib/captionStyles";
import { Card } from "@/components/ui/Card";

/**
 * Shows the caption presets before sign-up, driven by the same
 * `CAPTION_PRESETS` the studio picker and the renderer use — so this can't
 * advertise a look the product doesn't actually produce.
 */
export function CaptionStyles() {
  const [activeId, setActiveId] = useState(CAPTION_PRESETS[0].id);
  const active = CAPTION_PRESETS.find((p) => p.id === activeId) ?? CAPTION_PRESETS[0];
  const words = ["captions", "that", "land", "on", "the", "beat"];
  const perLine = active.style.max_words_per_line;
  const lines: string[][] = [];
  for (let i = 0; i < words.length; i += perLine) lines.push(words.slice(i, i + perLine));

  const align =
    active.style.position === "middle"
      ? "items-center"
      : active.style.position === "top_third"
        ? "items-start"
        : "items-end";

  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">Caption styles</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          The part that actually holds attention
        </h2>
        <p className="max-w-xl text-sm text-white/50">
          Captions are timed per word by faster-whisper, so the active word highlights on the
          syllable it&apos;s spoken. Pick how that looks — size, colour, placement and how many words
          sit on screen at once.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr] lg:items-start">
        <div className="flex flex-col gap-2">
          {CAPTION_PRESETS.map((preset) => {
            const selected = preset.id === activeId;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => setActiveId(preset.id)}
                className={clsx(
                  "flex items-center gap-3 rounded-lg border p-3 text-left transition-all duration-200",
                  selected
                    ? "border-accent bg-accent/10"
                    : "border-border bg-surface hover:border-border-strong hover:bg-surface-hover"
                )}
              >
                <span
                  className="h-8 w-8 shrink-0 rounded-md border border-white/10"
                  style={{ backgroundColor: preset.previewHighlight }}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{preset.name}</span>
                  <span className="block truncate text-[11px] text-white/40">
                    {preset.description}
                  </span>
                </span>
              </button>
            );
          })}
        </div>

        <Card className="flex justify-center bg-surface-raised p-6">
          <div
            className={clsx(
              "relative flex aspect-[9/16] w-full max-w-[260px] justify-center overflow-hidden rounded-xl bg-gradient-to-br from-neutral-600 via-neutral-800 to-neutral-900 p-5",
              align
            )}
          >
            <p
              className={clsx(
                "text-center font-extrabold leading-tight",
                active.style.uppercase ? "uppercase" : "normal-case",
                active.style.font_size >= 90
                  ? "text-2xl"
                  : active.style.font_size >= 84
                    ? "text-xl"
                    : "text-lg"
              )}
              style={{ textShadow: `0 0 ${active.style.outline_width * 1.5}px #000, 0 2px 4px #000` }}
            >
              {lines.map((line, li) => (
                <span key={li} className="block">
                  {line.map((word, wi) => (
                    <span
                      key={word}
                      style={{
                        // One highlighted word per line stands in for the
                        // moving karaoke cursor.
                        color: wi === (li === 0 ? 0 : 1) ? active.previewHighlight : "#fff",
                      }}
                    >
                      {word}{" "}
                    </span>
                  ))}
                </span>
              ))}
            </p>
          </div>
        </Card>
      </div>
    </section>
  );
}
