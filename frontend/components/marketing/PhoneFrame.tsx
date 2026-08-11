"use client";

import clsx from "clsx";
import { Bookmark, Heart, MessageCircle, Music2, Plus, Reply } from "lucide-react";

/**
 * An iPhone showing the render inside a TikTok feed.
 *
 * The point of the framing: a 9:16 file on a page is an abstraction, and
 * the thing people actually want to know is what it looks like where they
 * are going to post it. So the screen is a real phone aspect (19.5:9), the
 * video is letterboxed inside it exactly as TikTok letterboxes a 9:16
 * upload on a tall display, and the feed chrome sits on top.
 *
 * The action rail deliberately carries no counts. Numbers there would be
 * invented engagement on output that has never been posted — the same
 * fabrication as a made-up testimonial, just drawn as an icon. The icons
 * alone say "this is where it goes"; a number would say "and it did this".
 */
export function PhoneFrame({
  src,
  poster,
  caption,
  handle = "@shortpulse",
  className,
  autoPlay = true,
}: {
  src: string;
  poster?: string;
  caption: string;
  handle?: string;
  className?: string;
  autoPlay?: boolean;
}) {
  return (
    <div className={clsx("relative mx-auto w-full max-w-[290px]", className)}>
      <div className="pointer-events-none absolute -inset-8 -z-10 rounded-full bg-accent/20 blur-3xl" />

      {/* Side buttons, drawn behind the body so only the sliver that would
          stick out past the frame is visible. */}
      <span
        aria-hidden
        className="absolute -left-[3px] top-[17%] h-7 w-[3px] rounded-l bg-gradient-to-b from-neutral-600 to-neutral-800"
      />
      <span
        aria-hidden
        className="absolute -left-[3px] top-[25%] h-12 w-[3px] rounded-l bg-gradient-to-b from-neutral-600 to-neutral-800"
      />
      <span
        aria-hidden
        className="absolute -left-[3px] top-[37%] h-12 w-[3px] rounded-l bg-gradient-to-b from-neutral-600 to-neutral-800"
      />
      <span
        aria-hidden
        className="absolute -right-[3px] top-[28%] h-16 w-[3px] rounded-r bg-gradient-to-b from-neutral-600 to-neutral-800"
      />

      {/* Titanium rail: a thin gradient ring is what separates a phone from
          a rounded rectangle at this size. */}
      <div className="relative rounded-[2.75rem] bg-gradient-to-br from-neutral-500 via-neutral-800 to-neutral-600 p-[2px] shadow-2xl shadow-black/60">
        <div className="rounded-[2.65rem] bg-black p-[9px]">
          <div className="relative aspect-[9/19.5] overflow-hidden rounded-[2.1rem] bg-black">
            {/* Blurred fill behind the letterbox bars, the way every feed
                app handles a video that doesn't match the screen. Without
                it the bars are dead black, which swallows the Dynamic
                Island and makes the phone read as a plain rectangle. The
                poster is used rather than a second <video> so this costs
                one image decode instead of a whole extra stream. */}
            {poster && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={poster}
                alt=""
                aria-hidden
                className="absolute inset-0 h-full w-full scale-110 object-cover blur-xl brightness-[0.45]"
              />
            )}

            <video
              src={src}
              poster={poster}
              autoPlay={autoPlay}
              muted
              loop
              playsInline
              preload="metadata"
              // `contain`, not `cover`: cover would crop the 9:16 render to
              // the taller screen and eat the outer edges of the burned-in
              // captions, which run to within 60px of the frame.
              className="absolute inset-0 h-full w-full object-contain"
            />

            <FeedChrome caption={caption} handle={handle} />

            {/* Dynamic Island sits above everything, as it does on device. */}
            <span
              aria-hidden
              className="absolute left-1/2 top-2 z-20 h-[22px] w-[76px] -translate-x-1/2 rounded-full bg-black"
            />
            <span
              aria-hidden
              className="absolute bottom-1.5 left-1/2 z-20 h-[3px] w-[92px] -translate-x-1/2 rounded-full bg-white/70"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function FeedChrome({ caption, handle }: { caption: string; handle: string }) {
  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex flex-col justify-between">
      {/* Top tabs. Real TikTok puts these over the video, unshaded. */}
      <div className="flex items-center justify-center gap-4 pt-9 text-[11px] font-medium">
        <span className="text-white/50">Following</span>
        <span className="relative text-white">
          For You
          <span className="absolute -bottom-1 left-1/2 h-[2px] w-5 -translate-x-1/2 rounded-full bg-white" />
        </span>
      </div>

      <div className="relative">
        {/* Scrim so the handle and caption stay legible over a bright
            frame — the app does the same thing. */}
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-black/75 via-black/30 to-transparent" />

        {/* Kept inside the bottom letterbox bar. Sitting any higher puts the
            feed's own caption on the same line as the burned-in one, which
            reads as a collision rather than as two layers. */}
        <div className="relative flex items-end justify-between gap-2 px-3 pb-3">
          <div className="min-w-0 flex-1 pb-1">
            <p className="text-[12px] font-semibold text-white drop-shadow">{handle}</p>
            <p className="mt-0.5 line-clamp-1 text-[11px] leading-snug text-white/90 drop-shadow">
              {caption}
            </p>
            <p className="mt-1 flex items-center gap-1 text-[10px] text-white/80 drop-shadow">
              <Music2 size={10} className="shrink-0" />
              <span className="truncate">original sound — {handle.replace("@", "")}</span>
            </p>
          </div>

          <ActionRail handle={handle} />
        </div>

        {/* Scrubber. Left at a fixed position rather than bound to the
            video: it reads as feed chrome, and a live one would pull
            attention off the render itself. */}
        <div className="relative mx-3 mb-4 h-[2px] rounded-full bg-white/25">
          <div className="h-full w-1/3 rounded-full bg-white/80" />
        </div>
      </div>
    </div>
  );
}

/**
 * Counts are omitted on purpose — see the note on PhoneFrame. The rail is
 * still recognisably TikTok's because the icon set and spacing carry it.
 */
function ActionRail({ handle }: { handle: string }) {
  return (
    <div className="flex shrink-0 flex-col items-center gap-4 pb-1">
      <div className="relative mb-1">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-white ring-1 ring-white/80">
          {handle.replace("@", "").slice(0, 2).toUpperCase()}
        </div>
        <span className="absolute -bottom-1.5 left-1/2 flex h-4 w-4 -translate-x-1/2 items-center justify-center rounded-full bg-[#fe2c55]">
          <Plus size={10} strokeWidth={3} className="text-white" />
        </span>
      </div>

      <Heart size={24} className="fill-white/95 text-white/95 drop-shadow" />
      <MessageCircle size={23} className="fill-white/95 text-white/95 drop-shadow" />
      <Bookmark size={22} className="fill-white/95 text-white/95 drop-shadow" />
      <Reply size={23} className="-scale-x-100 fill-white/95 text-white/95 drop-shadow" />

      {/* Spinning record, the one piece of the rail that is always in
          motion in the app. */}
      <div className="mt-0.5 flex h-7 w-7 animate-[spin_5s_linear_infinite] items-center justify-center rounded-full bg-gradient-to-br from-neutral-700 to-black ring-1 ring-white/20">
        <Music2 size={11} className="text-white/90" />
      </div>
    </div>
  );
}
