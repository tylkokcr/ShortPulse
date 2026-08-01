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
    <div className="flex flex-col gap-3">
      <p className="rounded-lg border border-accent/30 bg-accent/10 p-3 text-sm">
        <span className="font-medium text-accent">Hook: </span>
        {script.hook}
      </p>

      {script.scenes.map((scene, i) => {
        const range = ranges[i];
        const isActive = currentTime >= range.startS && currentTime < range.endS;
        return (
          <button
            key={scene.id}
            type="button"
            onClick={() => onSeek(range.startS)}
            className={clsx(
              "rounded-lg border p-3 text-left transition-colors",
              isActive ? "border-accent bg-accent/10" : "border-border hover:bg-surface-hover"
            )}
          >
            <div className="mb-1 flex items-center justify-between text-xs text-white/40">
              <span>Scene {scene.index + 1}</span>
              <span>{scene.duration_s.toFixed(1)}s</span>
            </div>
            <p className={clsx("text-sm", isActive ? "font-medium text-white" : "text-white/90")}>
              {scene.audio.voiceover_line}
            </p>
            <p className="mt-1.5 text-xs italic text-white/40">{scene.visual.prompt}</p>
          </button>
        );
      })}

      {script.call_to_action && (
        <p className="text-sm text-white/60">
          <span className="font-medium">CTA: </span>
          {script.call_to_action}
        </p>
      )}
    </div>
  );
}
