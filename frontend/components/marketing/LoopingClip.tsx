"use client";

import { useEffect, useRef } from "react";

/**
 * A short silent loop that plays only when it can be seen, and only for
 * someone who has not asked for less motion.
 *
 * The poster is the resting state, not a loading state: it is a real
 * frame of the same clip, so a visitor with reduced motion — or a browser
 * that will not autoplay — sees a finished picture rather than a gap.
 * Playback starts when the clip scrolls into view and pauses when it
 * leaves, so a page with it far below the fold costs nothing until then.
 */
export function LoopingClip({
  src,
  poster,
  width,
  height,
  label,
  className,
}: {
  src: string;
  poster: string;
  width: number;
  height: number;
  label: string;
  className?: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          // Autoplay can be refused even muted (power saving, a policy);
          // the poster is already showing, so a refusal needs no handling.
          video.play().catch(() => {});
        } else {
          video.pause();
        }
      },
      { threshold: 0.35 }
    );
    observer.observe(video);
    return () => observer.disconnect();
  }, []);

  return (
    <video
      ref={ref}
      src={src}
      poster={poster}
      width={width}
      height={height}
      muted
      loop
      playsInline
      preload="none"
      aria-label={label}
      className={className}
    />
  );
}
