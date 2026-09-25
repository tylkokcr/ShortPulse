"use client";

import { useRef, useState } from "react";

/**
 * A span picked out of a length of video.
 *
 * Lives here rather than in the editor it was written for because a
 * second screen now needs the same thing: the caption flow lets an
 * uploader choose which stretch of a long recording to take clips from,
 * and that is the same question as which stretch a title is on screen
 * for, at a different scale.
 *
 * What it replaces, in both places, is two number fields. Those were
 * accurate and told you nothing: the question anyone actually has is
 * whether the span covers the right moment, and a decimal cannot answer
 * that without playing the video and counting. Here the span is drawn
 * over the full duration, so the answer is the picture.
 *
 * Dragging is the primary control and the keyboard is not an
 * afterthought — each handle is a focusable slider that moves in tenths,
 * a second with shift — because this is exactly the kind of thing
 * somebody nudges frame by frame, and a drag alone cannot do that.
 *
 * The two callers differ in scale, so the floor is a prop: 200ms for an
 * overlay, two minutes for a stretch there is any point transcribing.
 * The labels are props for the same reason the floor is — the strings
 * belong to whichever screen is asking.
 */
/** mm:ss.d — tenths, because that is the precision the control edits in
 *  and a burned-in title landing a tenth late is visible. */
function stamp(ms: number): string {
  const clamped = Math.max(ms, 0);
  const total = Math.floor(clamped / 1000);
  const tenths = Math.floor((clamped % 1000) / 100);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}.${tenths}`;
}

/** What an overlay defaults to: nothing shorter is worth burning in,
 *  and it stops a handle dragged past its partner from inverting the
 *  span. A caller with a coarser floor passes its own. */
const DEFAULT_MIN_SPAN_MS = 200;
const STEP_MS = 100;

type Grab = { kind: "start" | "end" | "move"; grabMs: number };

export function TimelineRange({
  startMs,
  endMs,
  durationMs,
  playheadMs,
  onChange,
  onSeek,
  minSpanMs = DEFAULT_MIN_SPAN_MS,
  labels,
}: {
  startMs: number;
  endMs: number;
  durationMs: number;
  /** Where the video is. Omitted where nothing is playing. */
  playheadMs?: number;
  onChange: (startMs: number, endMs: number) => void;
  /** Given, the two timecodes become buttons that seek to themselves. */
  onSeek?: (seconds: number) => void;
  minSpanMs?: number;
  labels: { start: string; end: string };
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [grab, setGrab] = useState<Grab | null>(null);

  const pct = (ms: number) => Math.min(Math.max(ms / durationMs, 0), 1) * 100;

  function msAt(clientX: number): number {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return 0;
    const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
    return Math.round((ratio * durationMs) / STEP_MS) * STEP_MS;
  }

  function apply(kind: Grab["kind"], at: number, grabMs: number) {
    // Clamped to the video here rather than where the position comes
    // from: a drag is already bounded by the track it happens on, but
    // arrow keys are not, and an end held past the last frame stored a
    // span the render can never show.
    const inVideo = Math.min(Math.max(at, 0), durationMs);
    if (kind === "start") {
      onChange(Math.min(inVideo, endMs - minSpanMs), endMs);
    } else if (kind === "end") {
      onChange(startMs, Math.max(inVideo, startMs + minSpanMs));
    } else {
      // The whole span follows the pointer by the offset it was grabbed
      // at, so it does not jump its own width on the first movement, and
      // it stops at each end instead of being clipped by it.
      const span = endMs - startMs;
      const next = Math.min(Math.max(at - grabMs, 0), Math.max(durationMs - span, 0));
      onChange(next, next + span);
    }
  }

  // Takes the event rather than returning a handler: a factory called
  // during render puts the ref read inside a function the linter cannot
  // prove is deferred, and it is right to object — the deferral was an
  // accident of where the closure happened to be built.
  function startGrab(kind: Grab["kind"], event: React.PointerEvent) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setGrab({ kind, grabMs: kind === "move" ? msAt(event.clientX) - startMs : 0 });
  }

  function onPointerMove(event: React.PointerEvent) {
    if (!grab) return;
    apply(grab.kind, msAt(event.clientX), grab.grabMs);
  }

  function endGrab(event: React.PointerEvent) {
    if (!grab) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    setGrab(null);
  }

  function nudge(kind: "start" | "end", event: React.KeyboardEvent) {
    const step = event.shiftKey ? 1000 : STEP_MS;
    const delta = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
    if (!delta) return;
    event.preventDefault();
    apply(kind, (kind === "start" ? startMs : endMs) + delta, 0);
  }

  const handle =
    "absolute top-0 h-full w-4 -translate-x-1/2 cursor-ew-resize touch-none rounded-full " +
    "after:absolute after:inset-y-1 after:left-1/2 after:w-[3px] after:-translate-x-1/2 " +
    "after:rounded-full after:bg-accent after:transition-colors " +
    "hover:after:bg-accent-hover focus-visible:outline-none focus-visible:after:bg-white";

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <div
        ref={trackRef}
        className="relative h-7 w-full rounded-md border border-border bg-black/40"
        onPointerMove={onPointerMove}
        onPointerUp={endGrab}
        onPointerCancel={endGrab}
      >
        {/* Drag anywhere on the span to move it. aria-hidden rather than a
            button: there is no keyboard equivalent for moving both ends at
            once, and the two sliders below already reach every value this
            reaches — announcing a control that cannot be operated is worse
            than announcing nothing. */}
        <span
          aria-hidden
          onPointerDown={(event) => startGrab("move", event)}
          className="absolute top-0 h-full cursor-grab touch-none rounded-[3px] border-y border-accent/50 bg-accent/20 active:cursor-grabbing"
          style={{ left: `${pct(startMs)}%`, width: `${pct(endMs) - pct(startMs)}%` }}
        />

        {/* Where the video is, drawn over the span rather than under it.
            Under looked tidier until you noticed it vanished exactly when
            the playhead entered the span — which is the one moment it
            answers something, because that is the text being on screen.
            Absent when nothing is playing: a line pinned at zero would
            read as a position rather than as the lack of one. */}
        {playheadMs !== undefined && (
          <span
            aria-hidden
            className="pointer-events-none absolute top-0 h-full w-px bg-white/70"
            style={{ left: `${pct(playheadMs)}%` }}
          />
        )}

        <span
          role="slider"
          tabIndex={0}
          aria-label={labels.start}
          aria-valuemin={0}
          aria-valuemax={Math.round(durationMs / 1000)}
          aria-valuenow={startMs / 1000}
          aria-valuetext={stamp(startMs)}
          onPointerDown={(event) => startGrab("start", event)}
          onKeyDown={(event) => nudge("start", event)}
          className={handle}
          style={{ left: `${pct(startMs)}%` }}
        />
        <span
          role="slider"
          tabIndex={0}
          aria-label={labels.end}
          aria-valuemin={0}
          aria-valuemax={Math.round(durationMs / 1000)}
          aria-valuenow={endMs / 1000}
          aria-valuetext={stamp(endMs)}
          onPointerDown={(event) => startGrab("end", event)}
          onKeyDown={(event) => nudge("end", event)}
          className={handle}
          style={{ left: `${pct(endMs)}%` }}
        />
      </div>

      <div className="flex items-center gap-1 font-mono text-[10px] tabular-nums text-white/35">
        {/* Clicking a timecode seeks, the same as clicking one in the
            breakdown above — so checking the placement is one click
            rather than a scrub. Plain text where there is nothing to
            seek: a control that looks pressable and does nothing is
            worse than a label. */}
        <Timecode ms={startMs} onSeek={onSeek} />
        <span className="text-white/20">→</span>
        <Timecode ms={endMs} onSeek={onSeek} />
        <span className="ml-auto text-white/20">{stamp(durationMs)}</span>
      </div>
    </div>
  );
}


function Timecode({ ms, onSeek }: { ms: number; onSeek?: (seconds: number) => void }) {
  if (!onSeek) return <span className="px-1">{stamp(ms)}</span>;
  return (
    <button
      type="button"
      onClick={() => onSeek(ms / 1000)}
      className="rounded px-1 transition-colors hover:bg-surface-hover hover:text-white"
    >
      {stamp(ms)}
    </button>
  );
}
