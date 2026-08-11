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
 * These use the `stock_media` visual mode. The AI-stills mode was tried
 * here first and its output was not honest to show: diffusion at this size
 * mangles faces and hands (a render of this same sleep script produced a
 * doubled nose) and turns any on-screen text into scribble. Real footage
 * has none of those failure modes. `LIMITATIONS` on the landing page says
 * so out loud rather than letting these clips imply every mode looks like
 * this.
 */
interface Example {
  slug: string;
  title: string;
  language: string;
  seconds: number;
  scenes: number;
}

const EXAMPLES: Example[] = [
  { slug: "honey", title: "Why honey never spoils", language: "English", seconds: 24, scenes: 5 },
  { slug: "ocean", title: "Why the ocean is salty", language: "English", seconds: 19, scenes: 5 },
  { slug: "dreams-tr", title: "Neden gece rüya görürüz?", language: "Türkçe", seconds: 24, scenes: 5 },
  { slug: "lightning", title: "How lightning actually forms", language: "English", seconds: 23, scenes: 5 },
  { slug: "sky-es", title: "¿Por qué el cielo es azul?", language: "Español", seconds: 17, scenes: 5 },
  { slug: "coffee", title: "Why coffee wakes you up", language: "English", seconds: 24, scenes: 5 },
  { slug: "cats-tr", title: "Kediler neden kutuları sever?", language: "Türkçe", seconds: 12, scenes: 3 },
  { slug: "volcano", title: "Why volcanoes erupt", language: "English", seconds: 24, scenes: 5 },
  { slug: "goosebumps", title: "Why we get goosebumps", language: "English", seconds: 18, scenes: 5 },
  { slug: "sleep", title: "A simple trick for better sleep", language: "English", seconds: 19, scenes: 5 },
];

/**
 * Pexels' API terms require a visible link back to Pexels and credit to
 * the videographer. The pipeline records who shot each clip at fetch time;
 * this is that list, deduplicated across all ten videos.
 */
const FOOTAGE_CREDITS = [
  "khezez | خزاز", "Angela Roma", "Joolsmagools ®️", "Ron Lach", "K", "Bav Vadgama", "Sema",
  "Mizuno K", "Anna Shvets", "Adventure Studio", "Marina Leonova", "Pachon in Motion",
  "Matthias Groeneveld", "LauraB", "Darina Belonogova", "cottonbro studio", "Nicola Narracci",
  "Photoviewx", "Koushalya Karthikeyan", "Ana Sandu", "Nadezhda Moryak", "Michael Burrows",
  "Tima Miroshnichenko", "Emrah", "John Diez", "Mikhail Nilov", "Nikita Ryumshin", "Artem Podrez",
  "Muhtelifane", "aslı aydoğdu", "Bahri Gün", "Kakada Chuon", "JUN HO LEE", "Ben Prater",
  "Timur Weber", "Canan İldeniz", "Anna Pou", "Ambareesh Sridhar Photography", "Masha Glazova",
];

export function Examples() {
  return (
    <section className="py-16">
      <div className="mx-auto mb-8 flex max-w-6xl flex-col gap-2 px-6">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">Real output</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Ten videos this pipeline actually made
        </h2>
        <p className="max-w-xl text-sm text-white/50">
          Unedited output — AI-written script, Piper voiceover, word-synced captions and real stock
          footage, in three languages. Hover any one to play it.
        </p>
      </div>

      {/* Edges faded so clips enter and leave rather than being chopped off. */}
      <div className="relative [mask-image:linear-gradient(to_right,transparent,black_6%,black_94%,transparent)]">
        <div className="group flex w-max gap-4 animate-marquee hover:[animation-play-state:paused] motion-reduce:animate-none motion-reduce:overflow-x-auto">
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
          , filmed by {FOOTAGE_CREDITS.join(", ")}.
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
