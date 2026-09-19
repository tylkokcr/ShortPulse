"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
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
 *
 * Hovering one plays it. The motion is not an animation invented for the
 * page: it is the same zoompan Ken Burns move `render_scene_clip` applies
 * to a still, generated from these exact frames. A visitor hovering a card
 * is therefore watching what Fast Hybrid actually does with an image,
 * which is the one thing a grid of stills cannot say.
 *
 * One deliberate difference from the renderer: there the zoom runs one
 * way, because a scene plays once and is followed by the next one. These
 * loop, and a one-way zoom loops by snapping back — the frame jumped every
 * few seconds under the pointer. So the zoom and pan here follow a raised
 * cosine instead: out to the peak at the midpoint and back, which puts the
 * last frame on top of the first. Measured as the difference between those
 * two frames, the seam went from 11.8dB to 26-35dB, the remainder being
 * H.264 noise rather than anything that moves.
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
  const t = useTranslations("artStyles");
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
        <span className="font-mono text-xs uppercase tracking-widest text-accent">{t("eyebrow")}</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          {t("title")}
        </h2>
        <p className="max-w-xl text-sm text-white/50">
          {t("sub")}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {styles.map((style) => (
          <StyleCard key={style.id} style={style} />
        ))}
      </div>
    </section>
  );
}

function StyleCard({ style }: { style: ArtStyle }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  /**
   * Nothing is fetched until the pointer arrives: `preload="none"` plus a
   * poster means the resting grid costs six JPEGs, exactly what it cost
   * before. The clips start at zoom 1.0, so the first frame *is* the
   * poster — stopping resets to it and the card doesn't jump.
   *
   * A style whose clip is missing degrades to the still it always was:
   * play() rejects, the poster stays up, and nothing throws.
   */
  const play = () => {
    const video = videoRef.current;
    if (!video) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    void video.play().catch(() => {});
  };

  const stop = () => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.currentTime = 0;
  };

  return (
    <figure
      className="group flex flex-col gap-2.5"
      onMouseEnter={play}
      onMouseLeave={stop}
    >
      <div className="overflow-hidden rounded-md border border-border transition-all duration-300 group-hover:border-border-strong group-hover:shadow-xl group-hover:shadow-black/40">
        <video
          ref={videoRef}
          src={`/art-styles/${style.id}.mp4`}
          poster={`/art-styles/${style.sample}`}
          aria-label={`${style.name} example frame`}
          muted
          loop
          playsInline
          preload="none"
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
  );
}
