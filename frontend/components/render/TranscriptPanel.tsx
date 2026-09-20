"use client";

import { Megaphone } from "lucide-react";
import clsx from "clsx";
import type { ScriptOutput } from "@/lib/types";
import { SceneRegenerate } from "./SceneRegenerate";
import { SceneFeedback } from "./SceneFeedback";
import type { SceneFeedback as Verdict } from "@/lib/types";
import { sceneThumbUrl } from "@/lib/api";

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

/**
 * Re-rolling is optional and injected, so this stays a presentational
 * component: the page owns the project and the request, and this owns the
 * shot list. Absent — a self-hosted install, a project whose working
 * files were swept — the panel renders exactly as it did before.
 */
interface FeedbackProps {
  /** This viewer's existing verdicts, keyed by scene index. */
  verdicts: Map<number, Verdict>;
  onFlag: (index: number, reason: string, note: string) => Promise<void>;
}

interface RegenerateProps {
  canRegenerate: boolean;
  blockedReason?: string | null;
  /** Which scene is being re-drawn, if any. Everything else is disabled
   *  while one runs: they contend for the same server-side lock and would
   *  come back 409. */
  busyIndex: number | null;
  onRegenerate: (index: number, prompt: string, negativePrompt: string) => Promise<void>;
}

export function TranscriptPanel({
  script,
  currentTime,
  onSeek,
  regenerate,
  feedback,
  projectId,
  thumbToken,
}: {
  script: ScriptOutput;
  currentTime: number;
  onSeek: (seconds: number) => void;
  regenerate?: RegenerateProps;
  feedback?: FeedbackProps;
  /** Signed credential for the scene frames. Absent until the render
   *  finishes, and absent forever on a project whose clips were swept —
   *  the rows fall back to the prompt on its own. */
  projectId?: string;
  thumbToken?: string | null;
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
            <li key={scene.id} className="group/scene relative">
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
                {/* The frame this scene actually produced.
                    A prompt — "a portrait with an intense gaze" — does not
                    tell anyone which picture came out of it, so the list
                    was unreadable without scrubbing the player, and the
                    two controls under each row were unusable until you
                    had. onError hides it rather than showing a broken
                    image: an older render has no clip left to take a
                    frame from, and the row reads exactly as it used to. */}
                <span className="flex shrink-0 flex-col items-center gap-1">
                  {projectId && thumbToken && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={sceneThumbUrl(projectId, i, thumbToken)}
                      alt=""
                      loading="lazy"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                      className={clsx(
                        "h-[68px] w-[38px] rounded-sm border object-cover transition-colors",
                        isActive ? "border-accent/60" : "border-border"
                      )}
                    />
                  )}
                  <span
                    className={clsx(
                      "font-mono text-[10px] tabular-nums transition-colors",
                      isActive ? "text-accent" : "text-white/30 group-hover:text-white/50"
                    )}
                  >
                    {formatTimecode(range.startS)}
                  </span>
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

              {/* A sibling of the seek button, not a child: a button
                  inside a button is invalid and the nested one stops
                  receiving clicks in some browsers. */}
              {!scene.is_outro && (feedback || regenerate?.canRegenerate) && (
                // One quiet row, not a stack.
                //
                // These were hidden on hover for a while, which was the
                // wrong instrument twice over: `opacity-0` still occupies
                // its space, so every unhovered scene grew a band of dead
                // air, and a stacked column stretched two secondary
                // actions to the full width of the panel until they read
                // as the row rather than as tools on it. Hiding also puts
                // them out of reach of a keyboard.
                //
                // Small and side by side solves what hiding was aiming at
                // — twelve pairs of buttons stop competing with the
                // twelve things they act on — without costing layout or
                // access. Wrapping lets either one open to full width.
                <div className="flex flex-wrap items-start gap-2 pb-3 pl-14 pr-2">
                  {/* The complaint sits directly above the fix, so "this
                      is wrong" is answered by "then draw it again"
                      rather than by a thank-you. */}
                  {feedback && (
                    <SceneFeedback
                      index={i}
                      verdict={feedback.verdicts.get(i)}
                      canReRoll={Boolean(regenerate?.canRegenerate)}
                      onSubmit={feedback.onFlag}
                    />
                  )}
                  {regenerate?.canRegenerate && (
                    <SceneRegenerate
                      scene={scene}
                      index={i}
                      busy={regenerate.busyIndex === i}
                      disabled={
                        regenerate.busyIndex !== null && regenerate.busyIndex !== i
                      }
                      onRegenerate={regenerate.onRegenerate}
                    />
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {/* Said once, under the list, rather than as a disabled control on
          every scene. Every video rendered before re-rolling existed lands
          here, and so does every one past its retention window — an
          explanation is more use than a button that always fails. */}
      {regenerate && !regenerate.canRegenerate && regenerate.blockedReason && (
        <p className="border-t border-border pt-3 text-[11px] leading-relaxed text-white/30">
          {regenerate.blockedReason}
        </p>
      )}

      {/* The call to action, shown only when it is not already above.
          With the outro card on, render_manager appends the CTA as a real
          scene — so this block was printing the closing line twice, once
          as a scene with a timecode and once again underneath. With the
          card off it never reaches the video at all: it becomes the
          fallback for the post description, which is a different place
          and worth saying out loud, because a line sitting under the
          transcript in the same type as the scenes above reads as
          something that got spoken. */}
      {script.call_to_action && !script.scenes.some((scene) => scene.is_outro) && (
        <div className="mt-4 flex gap-3 rounded-lg border border-border bg-black/20 px-3 py-2.5">
          <Megaphone size={13} className="mt-0.5 shrink-0 text-white/30" />
          <div className="flex min-w-0 flex-col gap-1">
            <p className="text-sm leading-relaxed text-white/60">{script.call_to_action}</p>
            <p className="text-[11px] leading-relaxed text-white/30">
              Not in the video — the outro card is off. It fills in the post description if
              you publish without writing one.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function formatTimecode(seconds: number): string {
  const total = Math.max(Math.floor(seconds), 0);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
