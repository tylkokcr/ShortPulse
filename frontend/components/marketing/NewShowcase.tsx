"use client";

import { useRef, useState } from "react";
import clsx from "clsx";
import { Languages, Music2, Volume2, VolumeX } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/Badge";

/**
 * What is new, played rather than described: two phones, each with the
 * one control that makes the feature obvious.
 *
 * Both are real output of this pipeline, made from footage anyone may use
 * commercially (Pexels) and music the repository licenses
 * (app/assets/music/ATTRIBUTION.md):
 *
 * - The beat edit is nine stock clips, each trimmed to its moment the way
 *   a user would before uploading, cut by the beat-edit engine to "Winning
 *   Spirit" in all three styles from the same seed. Switching style is the
 *   pitch — the same footage, three edits.
 * - The caption demo is a Piper narration over stock octopus footage, run
 *   through the upload pipeline once per language with caption
 *   translation. English, German and Spanish were made locally; Turkish
 *   on the live service, because the local model's Turkish was not good
 *   enough to put on a landing page and the hosted one's is.
 *
 * Videos live in public/showcase and, like public/examples, are not in git
 * (see public/examples/README.md for getting them onto the server).
 */
const STYLES = ["energetic", "cinematic", "calm"] as const;
type Style = (typeof STYLES)[number];

const SOURCES = [
  "08_freestyle",
  "02_snowboard",
  "03_skateboard",
  "04_bmx",
  "06_surfing",
  "00_surfing",
  "01_motocross",
  "07_parkour",
  "09_skateboard",
];

// Only renders whose translation reads right. German and Spanish were
// first made with the local model and came out wrong in ways a native
// speaker sees at once ("cuando un pulpo nata"), so they wait for renders
// from the live service, as Turkish was made.
const LANGUAGES = [
  {
    code: "en",
    label: "English",
    text: "An octopus has three hearts. Two of them pump blood through its gills. The third keeps the rest of its body alive. But when an octopus swims, that third heart stops beating. Which is why it would rather crawl.",
  },
  {
    code: "tr",
    label: "Türkçe",
    text: "Bir ahtapotun üç kalbi vardır. İkisi, kanı solungaçlarından pompalıyor. Üçüncü kalp ise vücudunun geri kalanını canlı tutuyor. Ama bir ahtapot yüzdüğünde, o üçüncü kalp atmayı durdurur. Bu yüzden sürünmeyi tercih eder.",
  },
] as const;
type Language = (typeof LANGUAGES)[number]["code"];

const FOOTAGE = [
  "ArtHouse Studio", "Tom Fisk", "Alex Moliski", "cottonbro studio", "Luke Cromwell",
  "Marc Espejo", "Collab Media", "Italo Bicca", "Entdecker Fuchs", "JUN HO LEE",
];

function Phone({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative aspect-[9/16] w-[150px] shrink-0 overflow-hidden rounded-[22px] border border-border-strong bg-black shadow-2xl shadow-black/60 sm:w-[210px]">
      {children}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={clsx(
        "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "border-accent bg-accent/15 text-white"
          : "border-border text-white/55 hover:border-border-strong hover:text-white"
      )}
    >
      {children}
    </button>
  );
}

function InputLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-widest text-white/35">{children}</span>
  );
}

function Feature({
  icon: Icon,
  title,
  body,
  input,
  phone,
  controlLabel,
  controls,
}: {
  icon: typeof Music2;
  title: string;
  body: string;
  input: React.ReactNode;
  phone: React.ReactNode;
  controlLabel: string;
  controls: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start gap-3 lg:min-h-[88px]">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent/15 text-accent">
          <Icon size={16} />
        </span>
        <div className="flex flex-col gap-1">
          <h3 className="text-base font-semibold">{title}</h3>
          <p className="text-sm leading-relaxed text-white/50">{body}</p>
        </div>
      </div>
      <div className="flex items-center gap-4 sm:gap-6">
        <div className="flex min-w-0 flex-1 flex-col gap-2">{input}</div>
        {phone}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs text-white/40">{controlLabel}</span>
        {controls}
      </div>
    </div>
  );
}

function SoundToggle({ muted, onToggle }: { muted: boolean; onToggle: () => void }) {
  const t = useTranslations("showcase");
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={t(muted ? "soundOn" : "soundOff")}
      className="absolute bottom-3 right-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white/80 backdrop-blur hover:text-white"
    >
      {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
    </button>
  );
}

export function NewShowcase() {
  const t = useTranslations("showcase");
  const tb = useTranslations("studio.beat");
  const [style, setStyle] = useState<Style>("energetic");
  // Opens in the visitor's own language when there is a render of it —
  // a Turkish visitor reading Turkish captions over English speech is
  // the feature, shown before any button is pressed.
  const locale = useLocale();
  const [language, setLanguage] = useState<Language>(
    LANGUAGES.find((l) => l.code === locale)?.code ?? "en"
  );
  const current = LANGUAGES.find((l) => l.code === language) ?? LANGUAGES[0];
  const [beatMuted, setBeatMuted] = useState(true);
  const [captionMuted, setCaptionMuted] = useState(true);
  const captionVideo = useRef<HTMLVideoElement>(null);
  const resumeAt = useRef(0);

  function pickLanguage(next: Language) {
    // Same moment, other language: the narration does not restart, only
    // the words on screen change — which is the feature.
    resumeAt.current = captionVideo.current?.currentTime ?? 0;
    setLanguage(next);
  }

  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-10 flex flex-col gap-2">
        <Badge tone="accent" className="w-fit">
          {t("badge")}
        </Badge>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
        <p className="max-w-xl text-sm text-white/50">{t("sub")}</p>
      </div>

      {/* Two columns built the same way, so they read as a pair: what the
          feature is, what goes in beside what comes out (the phone, the
          same size on both sides), and the one control under it. */}
      <div className="grid grid-cols-1 gap-14 lg:grid-cols-2 lg:gap-10">
        <Feature
          icon={Music2}
          title={t("beat.title")}
          body={t("beat.body")}
          input={
            <>
              <InputLabel>{t("beat.in")}</InputLabel>
              <div className="grid grid-cols-3 gap-1.5">
                {SOURCES.map((name) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={name}
                    src={`/showcase/src-${name}.jpg`}
                    alt=""
                    loading="lazy"
                    className="aspect-video w-full rounded object-cover opacity-80"
                  />
                ))}
              </div>
              <span className="flex items-center gap-1.5 text-[11px] text-white/40">
                <Music2 size={11} /> Winning Spirit · 123 BPM
              </span>
            </>
          }
          phone={
            <Phone>
              <video
                key={style}
                src={`/showcase/beat-${style}.mp4`}
                poster={`/showcase/beat-${style}.jpg`}
                autoPlay
                loop
                muted={beatMuted}
                playsInline
                preload="metadata"
                className="h-full w-full object-cover"
              />
              <SoundToggle muted={beatMuted} onToggle={() => setBeatMuted((m) => !m)} />
            </Phone>
          }
          controlLabel={t("beat.style")}
          controls={STYLES.map((s) => (
            <Chip key={s} active={style === s} onClick={() => setStyle(s)}>
              {tb(`styles.${s}.name`)}
            </Chip>
          ))}
        />

        <Feature
          icon={Languages}
          title={t("captions.title")}
          body={t("captions.body")}
          input={
            <>
              <InputLabel>{t("captions.in")}</InputLabel>
              <blockquote
                key={language}
                className="animate-fade-up rounded-md border border-border bg-black/30 p-3 text-[13px] leading-relaxed text-white/75"
              >
                {current.text}
              </blockquote>
              <span className="flex items-center gap-1.5 text-[11px] text-white/40">
                <Languages size={11} /> {t("captions.voice")} · {current.label}
              </span>
            </>
          }
          phone={
            <Phone>
              <video
                ref={captionVideo}
                key={language}
                src={`/showcase/octo-${language}.mp4`}
                poster={`/showcase/octo-${language}.jpg`}
                autoPlay
                loop
                muted={captionMuted}
                playsInline
                preload="metadata"
                onLoadedMetadata={(e) => {
                  if (resumeAt.current) e.currentTarget.currentTime = resumeAt.current;
                }}
                className="h-full w-full object-cover"
              />
              <SoundToggle muted={captionMuted} onToggle={() => setCaptionMuted((m) => !m)} />
            </Phone>
          }
          controlLabel={t("captions.language")}
          controls={LANGUAGES.map((l) => (
            <Chip key={l.code} active={language === l.code} onClick={() => pickLanguage(l.code)}>
              {l.label}
            </Chip>
          ))}
        />
      </div>

      <p className="mt-10 text-xs leading-relaxed text-white/30">
        {t("credits", { names: FOOTAGE.join(", ") })}
      </p>
    </section>
  );
}
