"use client";

import { useRef, useState } from "react";
import { Volume2, VolumeX, Play } from "lucide-react";
import clsx from "clsx";
import { Badge } from "@/components/ui/Badge";

/**
 * Real renders, not mockups.
 *
 * Every clip here came out of this pipeline and lives in
 * `frontend/public/examples` (transcoded down from the original 1080x1920
 * masters for page weight — same frames, same audio, lower bitrate).
 * Durations and scene counts are read off the rendered projects rather
 * than chosen to look good.
 *
 * Ten are `stock_media` and one is `fast_hybrid`, marked on the card.
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
interface Example {
  slug: string;
  title: string;
  language: string;
  seconds: number;
  scenes: number;
  /** Marked only on the AI-stills entries. Absent means stock footage,
   *  which is what most of these are and what the credit line below
   *  covers — a generated clip has no videographer to name. */
  aiStills?: boolean;
}

const EXAMPLES: Example[] = [
  { slug: "honey", title: "Why honey never spoils", language: "English", seconds: 24, scenes: 5 },
  { slug: "dreams-tr", title: "Neden gece rüya görürüz?", language: "Türkçe", seconds: 18, scenes: 5 },
  { slug: "moon-fr", title: "Pourquoi la lune change-t-elle de forme ?", language: "Français", seconds: 25, scenes: 6 },
  { slug: "ocean", title: "Why the ocean is salty", language: "English", seconds: 19, scenes: 5 },
  { slug: "leaves-de", title: "Warum färben sich Blätter im Herbst?", language: "Deutsch", seconds: 20, scenes: 5 },
  { slug: "sky-es", title: "¿Por qué el cielo es azul?", language: "Español", seconds: 17, scenes: 5 },
  { slug: "cats-ar", title: "لماذا تخاف القطط من الماء؟", language: "العربية", seconds: 21, scenes: 5 },
  { slug: "lightning", title: "How lightning actually forms", language: "English", seconds: 23, scenes: 5 },
  { slug: "yawn-pt", title: "Por que bocejamos?", language: "Português", seconds: 26, scenes: 5 },
  { slug: "coffee", title: "Why coffee wakes you up", language: "English", seconds: 24, scenes: 5 },
  { slug: "night-ru", title: "Почему небо ночью тёмное?", language: "Русский", seconds: 11, scenes: 5 },
  { slug: "cats-tr", title: "Kediler neden kutuları sever?", language: "Türkçe", seconds: 22, scenes: 5 },
  { slug: "espresso-it", title: "Perché il caffè ci sveglia?", language: "Italiano", seconds: 16, scenes: 5 },
  { slug: "volcano", title: "Why volcanoes erupt", language: "English", seconds: 24, scenes: 5 },
  { slug: "goosebumps", title: "Why we get goosebumps", language: "English", seconds: 18, scenes: 5 },
  { slug: "sleep", title: "A simple trick for better sleep", language: "English", seconds: 19, scenes: 5 },
  // The one AI-stills entry, and the reason the comment above no longer
  // applies. Numbers read off the render: 8 scenes, 23.6s, photoreal.
  {
    slug: "quiet-observers",
    title: "Why quiet people read the room",
    language: "English",
    seconds: 24,
    scenes: 8,
    aiStills: true,
  },
];

/**
 * Pexels' API terms require a visible link back to Pexels and credit to
 * the videographer. The pipeline records who shot each clip at fetch time;
 * this is that list, deduplicated across all sixteen stock-footage videos.
 */
const FOOTAGE_CREDITS = [
  "Aaron Burden", "Abdullah | 4K", "Adventure Studio", "Alexey Chudin",
  "Ambareesh Sridhar Photography", "Ana Sandu", "Angela Roma", "Anna Pou", "Anna Shvets",
  "Artem Podrez", "aslı aydoğdu", "Bahri Gün", "Bav Vadgama", "Ben Prater",
  "Canan İldeniz", "cottonbro studio", "Darina Belonogova", "Deti riyanti", "Ebahir",
  "Emrah", "Hale Ş", "Iceberg San", "Ilya Lyzhin", "John Diez", "Joolsmagools ®️",
  "Juan Camilo Trujillo  Botero 🇨🇴📸", "JUN HO LEE", "K", "Kakada Chuon", "khezez | خزاز",
  "Koushalya Karthikeyan", "LauraB", "Lentes  Bella", "Marina Leonova", "Masha Glazova",
  "Matthias Groeneveld", "Max Medyk", "Michael Burrows", "Mikhail Nilov", "Mizuno K",
  "Muhtelifane", "Nadezhda Moryak", "Nicola Narracci", "Nikita Ryumshin",
  "Pachon in Motion", "Pavel Danilyuk", "Photoviewx", "RDNE Stock project",
  "ROMAN ODINTSOV", "Ron Lach", "Sema", "Shan Ali", "Stefanie Jockschat",
  "Tima Miroshnichenko", "Timur Weber", "Toni.063371 -  Antonio Sáez", "Şahin Doğdu"
];

export function Examples() {
  return (
    <section className="py-16">
      <div className="mx-auto mb-8 flex max-w-6xl flex-col gap-2 px-6">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">Real output</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Seventeen videos this pipeline actually made
        </h2>
        <p className="max-w-xl text-sm text-white/50">
          Unedited output — AI-written script, Piper voiceover, word-synced captions, in all nine
          languages the product offers. Sixteen use real stock footage; the one marked AI stills was
          drawn by the paid mode. Hover any one to play it.
        </p>
      </div>

      {/* Edges faded so clips enter and leave rather than being chopped off.
          overflow-hidden is load-bearing, not tidiness: the track below is
          w-max over twenty cards — some 4300px — and a mask only fades
          pixels, it does not clip layout. Without it that width lands in the
          document's scroll width and the whole page scrolls sideways on a
          phone. motion-reduce keeps the strip reachable when the animation
          that would have brought the rest into view is off. */}
      <div className="relative overflow-hidden motion-reduce:overflow-x-auto [mask-image:linear-gradient(to_right,transparent,black_6%,black_94%,transparent)]">
        <div className="group flex w-max gap-4 animate-marquee hover:[animation-play-state:paused] motion-reduce:animate-none">
          {/* Duplicated once so the -50% translate lands on an identical
              frame. aria-hidden on the copy keeps it out of the a11y tree. */}
          {[false, true].map((isClone) =>
            EXAMPLES.map((example) => (
              <ExampleCard
                key={`${example.slug}-${isClone}`}
                example={example}
                aria-hidden={isClone || undefined}
              />
            ))
          )}
        </div>
      </div>

      <div className="mx-auto mt-8 flex max-w-6xl flex-col gap-1.5 px-6 text-xs text-white/30">
        <p>
          Footage from{" "}
          <a
            href="https://www.pexels.com"
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2 hover:text-white/60"
          >
            Pexels
          </a>
          , filmed by {FOOTAGE_CREDITS.join(", ")}. The AI-stills clip has no footage to
          credit — every frame of it was generated.
        </p>
        <p>
          Background music is “Airport Lounge” by Kevin MacLeod (incompetech.com), licensed CC BY
          3.0 — the same royalty-free track the pipeline falls back to by default.
        </p>
      </div>
    </section>
  );
}

function ExampleCard({
  example,
  ...props
}: { example: Example } & React.HTMLAttributes<HTMLElement>) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [muted, setMuted] = useState(true);
  const [playing, setPlaying] = useState(false);

  function play() {
    // Rejects if the browser blocks playback or the pointer leaves before
    // it resolves. Nothing to recover from — the poster stays up.
    videoRef.current?.play().catch(() => {});
  }

  function stop() {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.currentTime = 0;
  }

  return (
    <figure
      className="w-[168px] shrink-0 sm:w-[200px]"
      onMouseEnter={play}
      onMouseLeave={stop}
      {...props}
    >
      <div className="relative overflow-hidden rounded-md border border-border bg-black transition-all duration-300 hover:border-border-strong hover:shadow-xl hover:shadow-black/40">
        <video
          ref={videoRef}
          src={`/examples/${example.slug}.mp4`}
          poster={`/examples/${example.slug}.jpg`}
          muted={muted}
          loop
          playsInline
          preload="none"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onClick={play}
          className="aspect-[9/16] w-full object-cover"
        />

        {!playing && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-black/60 backdrop-blur">
              <Play size={14} className="translate-x-[1px] fill-white text-white" />
            </span>
          </div>
        )}

        <button
          type="button"
          onClick={() => setMuted((m) => !m)}
          aria-label={muted ? "Unmute" : "Mute"}
          className="absolute bottom-2 right-2 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white/80 backdrop-blur transition-colors hover:bg-black/80 hover:text-white"
        >
          {muted ? <VolumeX size={12} /> : <Volume2 size={12} />}
        </button>

        <Badge
          tone="neutral"
          className={clsx(
            "absolute left-2 top-2 border-white/10 bg-black/60 px-2 py-0.5 text-[10px] text-white/70 backdrop-blur",
            example.language !== "English" && "border-accent/40 text-accent"
          )}
        >
          {example.language}
        </Badge>

        {/* Said on the card rather than only in the paragraph below: a
            visitor deciding whether three credits is worth it needs to
            know which of these it buys, while they are looking at it. */}
        {example.aiStills && (
          <Badge
            tone="neutral"
            className="absolute right-2 top-2 border-accent/40 bg-black/60 px-2 py-0.5 text-[10px] text-accent backdrop-blur"
          >
            AI stills
          </Badge>
        )}
      </div>

      <figcaption className="mt-2.5 flex flex-col gap-0.5">
        <span className="truncate text-xs font-medium">{example.title}</span>
        <span className="font-mono text-[10px] text-white/35">
          {example.seconds}s · {example.scenes} scenes
        </span>
      </figcaption>
    </figure>
  );
}
