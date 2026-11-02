"use client";

import { useLocale, useTranslations } from "next-intl";
import { EXAMPLES } from "@/lib/examples";
import ShortPulseDemo from "./ShortPulseDemo";

/**
 * The whole flow in half a minute, right under the hero: a topic from the
 * trends card becomes a short, goes out to YouTube and TikTok, and lands
 * in the library. The five scene frames are Pexels footage (credited with
 * the examples); the library is the real example renders, under their own
 * titles.
 */
const SCENES: [string, string, string, string, string] = [
  "/demo/scene0.jpg",
  "/demo/scene1.jpg",
  "/demo/scene2.jpg",
  "/demo/scene3.jpg",
  "/demo/scene4.jpg",
];

const LIBRARY = EXAMPLES.filter((e) => !e.square && e.slug !== "ocean").map((e) => ({
  src: `/examples/${e.slug}.jpg`,
  title: e.title,
}));

const LOCALES = ["tr", "en", "pl", "de"] as const;

export function ProductDemo() {
  const t = useTranslations("landing.demo");
  const locale = useLocale();
  const demoLocale = LOCALES.find((l) => l === locale) ?? "en";

  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">{t("eyebrow")}</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
        <p className="max-w-xl text-sm text-white/50">{t("sub")}</p>
      </div>
      <ShortPulseDemo locale={demoLocale} assets={{ scenes: SCENES, library: LIBRARY }} />
    </section>
  );
}
