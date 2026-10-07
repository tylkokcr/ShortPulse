"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Pause, Play, RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import type { TrackAnalysis } from "@/lib/api";

function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The bar start nearest a time — where the window is allowed to sit, so
 *  the first cut is always on a downbeat. */
function snap(time: number, downbeats: number[]): number {
  if (downbeats.length === 0) return time;
  return downbeats.reduce((best, b) => (Math.abs(b - time) < Math.abs(best - time) ? b : best));
}

/**
 * Which stretch of the song the edit uses.
 *
 * The song's loudness drawn as a waveform, the drop marked on it, and a
 * window the length of the edit that can be dragged along it. It starts
 * where the server would choose — the drop about a third of the way in —
 * and snaps to bar starts as it moves, because a cut that begins between
 * beats puts every cut after it off the beat too.
 */
export function MusicWindow({
  analysis,
  lengthS,
  start,
  onStart,
  audioSrc,
}: {
  analysis: TrackAnalysis;
  lengthS: number;
  start: number;
  onStart: (seconds: number) => void;
  audioSrc: string | null;
}) {
  const t = useTranslations("studio.beat.window");
  const track = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; start: number } | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const stopAt = useRef<number | null>(null);
  const [playing, setPlaying] = useState(false);

  const duration = Math.max(analysis.duration_s, 0.1);
  const span = Math.min(lengthS, duration);
  const maxStart = Math.max(0, duration - span);
  const clamp = (s: number) => Math.min(Math.max(0, s), maxStart);

  useEffect(
    () => () => {
      audio.current?.pause();
      if (stopAt.current) window.clearTimeout(stopAt.current);
    },
    []
  );
  // A new window or a new song stops whatever was playing the old one;
  // the element's own pause event clears the button.
  useEffect(() => {
    audio.current?.pause();
  }, [start, lengthS, audioSrc]);

  function toggle() {
    if (!audioSrc) return;
    if (playing) {
      audio.current?.pause();
      setPlaying(false);
      return;
    }
    audio.current?.pause();
    const element = new Audio(audioSrc);
    element.currentTime = start;
    element.onended = () => setPlaying(false);
    element.onpause = () => setPlaying(false);
    audio.current = element;
    element
      .play()
      .then(() => {
        setPlaying(true);
        if (stopAt.current) window.clearTimeout(stopAt.current);
        stopAt.current = window.setTimeout(() => {
          element.pause();
          setPlaying(false);
        }, span * 1000);
      })
      .catch(() => setPlaying(false));
  }

  function onPointerDown(event: React.PointerEvent) {
    drag.current = { x: event.clientX, start };
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
  }
  function onPointerMove(event: React.PointerEvent) {
    if (!drag.current || !track.current) return;
    const width = track.current.getBoundingClientRect().width || 1;
    const moved = ((event.clientX - drag.current.x) / width) * duration;
    onStart(clamp(snap(clamp(drag.current.start + moved), analysis.downbeats)));
  }
  function onPointerUp() {
    drag.current = null;
  }
  function onKeyDown(event: React.KeyboardEvent) {
    // A bar at a time, the same steps the pointer snaps to.
    const bars = analysis.downbeats;
    const index = bars.findIndex((b) => Math.abs(b - start) < 0.05);
    if (event.key === "ArrowRight" && index >= 0 && index < bars.length - 1) {
      onStart(clamp(bars[index + 1]));
      event.preventDefault();
    } else if (event.key === "ArrowLeft" && index > 0) {
      onStart(clamp(bars[index - 1]));
      event.preventDefault();
    }
  }

  const suggested = analysis.suggested_starts[String(lengthS)];
  const moved = suggested !== undefined && Math.abs(suggested - start) > 0.05;

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={track}
        className="relative h-14 select-none overflow-hidden rounded-md border border-border bg-black/40 touch-none"
      >
        {/* The song. */}
        <div className="absolute inset-0 flex items-center gap-px px-1">
          {analysis.envelope.map((level, i) => (
            <span
              key={i}
              className="flex-1 rounded-full bg-white/20"
              style={{ height: `${Math.max(6, level * 92)}%` }}
            />
          ))}
        </div>
        {/* The drop. */}
        {analysis.drop_s !== null && (
          <span
            className="absolute inset-y-0 w-px bg-white/60"
            style={{ left: `${(analysis.drop_s / duration) * 100}%` }}
            title={t("drop")}
          >
            <span className="absolute left-1 top-0.5 font-mono text-[9px] uppercase tracking-wider text-white/60">
              {t("drop")}
            </span>
          </span>
        )}
        {/* The stretch the edit uses. */}
        <div
          role="slider"
          tabIndex={0}
          aria-label={t("label")}
          aria-valuemin={0}
          aria-valuemax={Math.round(maxStart)}
          aria-valuenow={Math.round(start)}
          aria-valuetext={`${clock(start)} – ${clock(start + span)}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onKeyDown={onKeyDown}
          className="absolute inset-y-0 cursor-grab rounded-[3px] border-2 border-accent bg-accent/20 outline-none active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-accent/60"
          style={{ left: `${(start / duration) * 100}%`, width: `${(span / duration) * 100}%` }}
        />
      </div>
      <div className="flex items-center gap-3 text-xs">
        <button
          type="button"
          onClick={toggle}
          disabled={!audioSrc}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-white/70 hover:border-border-strong hover:text-white disabled:opacity-40"
        >
          {playing ? <Pause size={12} /> : <Play size={12} />}
          {t(playing ? "stop" : "play")}
        </button>
        <span className="font-mono text-[11px] text-white/50">
          {clock(start)} – {clock(start + span)}
        </span>
        <span className="font-mono text-[10px] text-white/30">{Math.round(analysis.tempo_bpm)} BPM</span>
        {moved && (
          <button
            type="button"
            onClick={() => onStart(clamp(suggested))}
            className={clsx("ml-auto flex items-center gap-1 text-white/45 hover:text-white")}
          >
            <RotateCcw size={11} />
            {t("reset")}
          </button>
        )}
      </div>
    </div>
  );
}
