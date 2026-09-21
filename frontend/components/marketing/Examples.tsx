"use client";

import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { Volume2, VolumeX, Play } from "lucide-react";
import clsx from "clsx";
import { Badge } from "@/components/ui/Badge";
import { EXAMPLES, FOOTAGE_CREDITS, type Example } from "@/lib/examples";

export function Examples() {
  const t = useTranslations("examples");

  return (
    <section className="py-16">
      <div className="mx-auto mb-8 flex max-w-6xl flex-col gap-2 px-6">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">
          {t("eyebrow")}
        </span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
        <p className="max-w-xl text-sm text-white/50">{t("intro")}</p>
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
