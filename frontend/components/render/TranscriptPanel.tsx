"use client";

import clsx from "clsx";
import type { ScriptOutput } from "@/lib/types";

interface SceneRange {
  startS: number;
  endS: number;
}

/**
 * Scenes are rendered back-to-back into one continuous clip, so a scene's
 * position in the final video is the sum of every prior scene's audio
 * duration — the same offset math subtitle_engine.py does server-side to
 * build the burned-in .ass captions.
 */
function computeSceneRanges(script: ScriptOutput): SceneRange[] {
  let offsetMs = 0;
  return script.scenes.map((scene) => {
    const durationMs = scene.audio.duration_ms ?? scene.duration_s * 1000;
    const range = { startS: offsetMs / 1000, endS: (offsetMs + durationMs) / 1000 };
    offsetMs += durationMs;
    return range;
  });
}

export function TranscriptPanel({
  script,
  currentTime,
  onSeek,
}: {
  script: ScriptOutput;
  currentTime: number;
  onSeek: (seconds: number) => void;
}) {
  const ranges = computeSceneRanges(script);

  return (
    <div className="flex flex-col">
      <div className="flex gap-3 pb-4">
        <span className="mt-0.5 w-10 shrink-0 font-mono text-[10px] uppercase tracking-widest text-accent">
          hook
        </span>
        <p className="text-sm leading-relaxed">{script.hook}</p>
      </div>

      {/* A continuous rail down the left, with each scene hanging off it.
          Reads as a shot list rather than a stack of identical cards —
          which is what it is, and the card-per-scene version gave every
          scene the same visual weight as the whole. */}
      <ol className="relative flex flex-col border-l border-border pl-0">
        {script.scenes.map((scene, i) => {
          const range = ranges[i];
          const isActive = currentTime >= range.startS && currentTime < range.endS;
          return (
            <li key={scene.id} className="relative">
              {/* Marks the scene playing right now, on the rail itself. */}
              <span
                aria-hidden
                className={clsx(
                  "absolute -left-px top-0 h-full w-px transition-colors duration-200",
                  isActive ? "bg-accent" : "bg-transparent"
                )}
              />
              <button
                type="button"
                onClick={() => onSeek(range.startS)}
                className={clsx(
                  "group flex w-full gap-3 py-3 pl-4 pr-2 text-left transition-colors",
                  isActive ? "bg-accent/[0.06]" : "hover:bg-surface-hover"
                )}
              >
                <span
                  className={clsx(
                    "mt-0.5 w-10 shrink-0 font-mono text-[10px] tabular-nums transition-colors",
                    isActive ? "text-accent" : "text-white/30 group-hover:text-white/50"
                  )}
                >
                  {formatTimecode(range.startS)}
                </span>
                <span className="min-w-0 flex-1">
                  <span
                    className={clsx(
                      "block text-sm leading-relaxed",
                      isActive ? "text-white" : "text-white/80"
                    )}
                  >
                    {scene.audio.voiceover_line}
                  </span>
                  <span className="mt-1 block truncate text-[11px] text-white/30">
                    {scene.visual.prompt}
                  </span>
                </span>
                <span className="mt-0.5 shrink-0 font-mono text-[10px] text-white/25">
                  {scene.duration_s.toFixed(1)}s
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {script.call_to_action && (
        <div className="flex gap-3 pt-4">
          <span className="mt-0.5 w-10 shrink-0 font-mono text-[10px] uppercase tracking-widest text-white/30">
            cta
          </span>
          <p className="text-sm leading-relaxed text-white/60">{script.call_to_action}</p>
        </div>
      )}
    </div>
  );
}

function formatTimecode(seconds: number): string {
  const total = Math.max(Math.floor(seconds), 0);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
