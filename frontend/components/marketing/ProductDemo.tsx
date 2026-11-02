"use client";

import { useLocale, useTranslations } from "next-intl";
import { EXAMPLES } from "@/lib/examples";
import ShortPulseDemoCarousel from "./demo/ShortPulseDemoCarousel";
import type { Locale } from "./demo/kit";

/**
 * The three studio modes, each played through once, right under the hero.
 *
 * Every image is footage we may show: the topic demo's scenes are Pexels
 * (matching its stock prompts), the talking head and the six edit clips
 * are Pexels too — the same sports clips the beat-edit showcase is cut
 * from — and all their videographers are in FOOTAGE_CREDITS. The library
 * cards are the real example renders under their own titles.
 *
 * Not on phones: the stage is 1120px wide and scales to a third there,
 * which leaves every label unreadable. The sections below it carry the
 * phone layout.
 */
const SCENES: [string, string, string, string, string] = [
  "/demo/scene0.jpg",
  "/demo/scene1.jpg",
  "/demo/scene2.jpg",
  "/demo/scene3.jpg",
  "/demo/scene4.jpg",
];
const CLIPS: [string, string, string, string, string, string] = [
  "/demo/clip0.jpg",
  "/demo/clip1.jpg",
  "/demo/clip2.jpg",
  "/demo/clip3.jpg",
  "/demo/clip4.jpg",
  "/demo/clip5.jpg",
];

const LIBRARY = EXAMPLES.filter((e) => !e.square && e.slug !== "ocean").map((e) => ({
  src: `/examples/${e.slug}.jpg`,
  title: e.title,
}));

const LOCALES: Locale[] = ["tr", "en", "pl", "de"];

export function ProductDemo() {
  const t = useTranslations("landing.demo");
  const locale = useLocale();
  const demoLocale = LOCALES.find((l) => l === locale) ?? "en";

  return (
    <section className="mx-auto hidden max-w-6xl px-6 py-16 sm:block">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">{t("eyebrow")}</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
        <p className="max-w-xl text-sm text-white/50">{t("sub")}</p>
      </div>
      <ShortPulseDemoCarousel
        locale={demoLocale}
        assets={{
          generate: { scenes: SCENES, library: LIBRARY },
          caption: { still: "/demo/talk.jpg" },
          edit: { clips: CLIPS },
        }}
      />
    </section>
  );
}
