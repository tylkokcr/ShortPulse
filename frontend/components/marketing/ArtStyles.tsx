"use client";

import { useEffect, useState } from "react";
import { listArtStyles } from "@/lib/api";
import type { ArtStyle } from "@/lib/types";

/**
 * The art styles, shown with the frames they actually produce.
 *
 * Same checkpoint, same settings, same subject prompt for all six — a
 * woman holding a coffee by a window, chosen because it contains a face
 * and hands. That is deliberate: those are exactly what diffusion gets
 * wrong at this size, and it is the honest reason the stylized looks exist
 * rather than an aesthetic preference.
 */
const FALLBACK: ArtStyle[] = [
  { id: "photoreal", name: "Photoreal", description: "Looks like footage.", sample: "photoreal.jpg", is_default: true },
  { id: "anime", name: "Anime", description: "Cel shading, clean line art.", sample: "anime.jpg", is_default: false },
  { id: "toon3d", name: "3D Toon", description: "Big-eyed animated-film look.", sample: "toon3d.jpg", is_default: false },
  { id: "comic", name: "Comic", description: "Inked outlines, halftone shading.", sample: "comic.jpg", is_default: false },
  { id: "clay", name: "Claymation", description: "Plasticine models.", sample: "clay.jpg", is_default: false },
  { id: "pixel", name: "Pixel Art", description: "Chunky 16-bit sprites.", sample: "pixel.jpg", is_default: false },
];

export function ArtStyles() {
  const [styles, setStyles] = useState<ArtStyle[]>(FALLBACK);

  useEffect(() => {
    listArtStyles()
      .then((list) => list.length && setStyles(list))
      .catch(() => {
        /* Keep the fallback so the section still sells with the API down. */
      });
  }, []);

  return (
    <section id="styles" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">Art styles</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Six looks, one prompt away
        </h2>
        <p className="max-w-xl text-sm text-white/50">
          Every frame below is a real render — same model, same settings, same subject. We picked a
          subject with a face and hands on purpose, because that&apos;s the hardest thing to get
          right and the reason most of these looks are stylized.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {styles.map((style) => (
          <figure key={style.id} className="group flex flex-col gap-2.5">
            <div className="overflow-hidden rounded-md border border-border transition-all duration-300 group-hover:border-border-strong group-hover:shadow-xl group-hover:shadow-black/40">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/art-styles/${style.sample}`}
                alt={`${style.name} example frame`}
                loading="lazy"
                className="aspect-[9/16] w-full object-cover transition-transform duration-500 group-hover:scale-105"
              />
            </div>
            <figcaption>
              <span className="block text-xs font-medium">{style.name}</span>
              <span className="mt-0.5 block text-[11px] leading-snug text-white/40">
                {style.description}
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
