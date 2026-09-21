"use client";

import { useRef, useState } from "react";
import { Play, Sparkles } from "lucide-react";
import clsx from "clsx";
import { EXAMPLES, FOOTAGE_CREDITS, type Example } from "@/lib/examples";
import { useShortPulseStore } from "@/lib/store";

/**
 * Somewhere to start, for the account that has just been created.
 *
 * A new user lands in the studio with five credits and an empty topic
 * field, having seen the examples on the marketing page and then left
 * them behind at the sign-in. The hardest part of a first render is not
 * the settings — every one of them already has a default — it is thinking
 * of the subject, and the cost of guessing wrong is a credit.
 *
 * So the same renders the landing page shows are offered here as starting
 * points: the clip plays on hover, and picking one fills in the topic,
 * language and mode it was actually made with. What comes out is the
 * user's own render, not a copy — the model writes a new script — but it
 * is a render whose shape they have already watched.
 *
 * Only the four fields we genuinely know are set. Art style, voice and
 * caption preset are not recorded per example, and inventing plausible
 * values would make the card a liar about what produced the clip beside
 * it.
 */
/**
 * Four, chosen rather than sampled.
 *
 * Randomising these was the first idea and it was wrong twice. It broke
 * hydration — Math.random runs once on the server and again on the client
 * and the two disagree — and, worse, a random draw from a list that is
 * mostly English stock footage usually shows four clips that look like
 * one capability.
 *
 * These four are a demonstration: both visual modes, three languages, and
 * a right-to-left script that is the single hardest thing here to believe
 * works without seeing it.
 */
const PICKED = ["ocean", "quiet-observers", "dreams-tr", "cats-ar"] as const;

export function StartFromExample({ className }: { className?: string }) {
  const setDraft = useShortPulseStore((s) => s.setDraft);
  const topic = useShortPulseStore((s) => s.draft.topic);

  const shown = PICKED.map((slug) => EXAMPLES.find((e) => e.slug === slug)!);

  function load(example: Example) {
    setDraft({
      topic: example.title,
      language: example.languageCode,
      visualMode: example.aiStills ? "fast_hybrid" : "stock_media",
      videoLength: "short",
    });
  }

  return (
    <div className={clsx("flex flex-col gap-3", className)}>
      <div className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold text-white/80">Start from an example</h2>
        <p className="text-xs text-white/35">
          Real renders. Picking one fills the form in — the script is still written fresh.
        </p>
      </div>

      <div className="flex flex-wrap gap-2.5">
        {shown.map((example) => (
          <ExampleTile
            key={example.slug}
            example={example}
            // Marked when the form is already showing this example, so
            // clicking twice does not look like nothing happened.
            loaded={topic === example.title}
            onLoad={() => load(example)}
          />
        ))}
      </div>

      {/* The Pexels licence asks for a visible link back and credit to the
          videographers wherever the footage is shown, and it is shown here
          now. The link stays on screen; the sixty names go behind a
          summary, because spelled out in full they were five lines of grey
          standing between the examples and the form. */}
      <details className="text-[11px] leading-relaxed text-white/25">
        <summary className="cursor-pointer list-none marker:hidden hover:text-white/40">
          Footage from{" "}
          <a
            href="https://www.pexels.com"
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="underline underline-offset-2 hover:text-white/50"
          >
            Pexels
          </a>
          , filmed by {FOOTAGE_CREDITS.length} videographers.
        </summary>
        <p className="mt-1.5">
          {FOOTAGE_CREDITS.join(", ")}. The AI-stills clip has no footage to credit — every
          frame of it was generated.
        </p>
      </details>
    </div>
  );
}

function ExampleTile({
  example,
  loaded,
  onLoad,
}: {
  example: Example;
  loaded: boolean;
  onLoad: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);

  return (
    <button
      type="button"
      onClick={onLoad}
      onMouseEnter={() => videoRef.current?.play().catch(() => {})}
      onMouseLeave={() => {
        const video = videoRef.current;
        if (!video) return;
        video.pause();
        video.currentTime = 0;
      }}
      className={clsx(
        "group flex w-[104px] flex-col gap-1.5 rounded-lg border p-1.5 text-left",
        "transition-[border-color,background-color] duration-200",
        "focus-visible:border-accent focus-visible:outline-none",
        loaded
          ? "border-accent/60 bg-accent/[0.08]"
          : "border-border hover:border-border-strong hover:bg-surface-hover"
      )}
    >
      <span className="relative block overflow-hidden rounded-md bg-black">
        <video
          ref={videoRef}
          src={`/examples/${example.slug}.mp4`}
          poster={`/examples/${example.slug}.jpg`}
          muted
          loop
          playsInline
          // Four clips at once is four downloads nobody asked for; the
          // poster is enough until a pointer lands on one.
          preload="none"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          className="aspect-[9/16] w-full object-cover"
        />
        {!playing && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-black/60 backdrop-blur">
              <Play size={12} className="translate-x-px fill-white text-white" />
            </span>
          </span>
        )}
        {example.aiStills && (
          // Not the Badge component: it is sized for the marketing cards
          // and overhung a tile a third of their width.
          <span className="absolute left-1 top-1 flex items-center gap-0.5 rounded bg-black/70 px-1 py-0.5 font-mono text-[8px] uppercase tracking-wide text-accent backdrop-blur">
            <Sparkles size={7} />
            AI
          </span>
        )}
      </span>

      <span className="line-clamp-2 min-h-[1.9rem] px-0.5 text-[11px] leading-snug text-white/70 group-hover:text-white">
        {example.title}
      </span>
      <span dir="ltr" className="px-0.5 font-mono text-[10px] text-white/30">
        <bdi>{example.language}</bdi> · {example.seconds}s
      </span>
    </button>
  );
}
