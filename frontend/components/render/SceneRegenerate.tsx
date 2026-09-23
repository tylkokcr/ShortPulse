"use client";

import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import type { Scene } from "@/lib/types";

/**
 * Re-drawing one scene's picture, from the shot list.
 *
 * Here rather than in a settings panel because this is where someone
 * notices the problem: they are reading the breakdown, looking at the
 * prompt that produced a frame they don't want. Every scene is an
 * independent sample, so the fix for one bad picture is one more sample —
 * not another render of the whole video, which resamples the scenes that
 * were fine.
 *
 * The price is on the button. This is the first thing in the product that
 * takes money after a render is finished, and a debit nobody expected is
 * the fastest route to a refund request.
 */
export function SceneRegenerate({
  scene,
  index,
  busy,
  disabled,
  onRegenerate,
}: {
  scene: Scene;
  index: number;
  busy: boolean;
  /** Something else is already changing this video, so the server would
   *  answer 409 — say so before the click rather than after. */
  disabled: boolean;
  onRegenerate: (index: number, prompt: string, negativePrompt: string) => Promise<void>;
}) {
  const t = useTranslations("app.regenerate");
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState(scene.visual.prompt);
  const [negative, setNegative] = useState(scene.visual.negative_prompt ?? "");

  if (!open) {
    return (
      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 font-mono text-[10px] text-white/40 transition-colors hover:border-border-strong hover:text-white/70 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? (
          <Loader2 size={11} className="animate-spin" />
        ) : (
          <RefreshCw size={11} />
        )}
        {busy ? t("redrawing") : t("reroll")}
        {(scene.visual.revision ?? 0) > 0 && !busy && (
          <span className="text-white/25">·{scene.visual.revision}</span>
        )}
      </button>
    );
  }

  return (
    <div className="flex w-full flex-col gap-2 rounded-lg border border-border bg-background p-3">
      <label className="flex flex-col gap-1">
        <span className="font-mono text-[10px] uppercase tracking-widest text-white/30">
          {t("whatToDraw")}
        </span>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={2}
          maxLength={400}
          className="resize-none rounded-md border border-border bg-surface px-2 py-1.5 text-xs leading-relaxed outline-none focus:border-border-strong"
        />
      </label>

      {/* The reason most people will open this. A hand came out with six
          fingers, so put hands in the negative and draw it again. Empty
          falls back to the art style's own negative prompt. */}
      <label className="flex flex-col gap-1">
        <span className="font-mono text-[10px] uppercase tracking-widest text-white/30">
          {t("whatToAvoid")}
        </span>
        <input
          value={negative}
          onChange={(e) => setNegative(e.target.value)}
          maxLength={400}
          // Prompt tokens, not UI: they go to the image model in English.
          placeholder="hands, crowd, text"
          className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs outline-none focus:border-border-strong"
        />
      </label>

      <div className="flex items-center gap-2 pt-0.5">
        <button
          type="button"
          disabled={busy || !prompt.trim()}
          onClick={async () => {
            await onRegenerate(index, prompt.trim(), negative.trim());
            setOpen(false);
          }}
          className="flex items-center gap-1.5 rounded-md bg-accent px-2.5 py-1.5 text-xs font-medium text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy && <Loader2 size={12} className="animate-spin" />}
          {busy ? t("drawing") : t("submit", { count: 1 })}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => setOpen(false)}
          className="rounded-md px-2 py-1.5 text-xs text-white/40 transition-colors hover:text-white/70"
        >
          {t("cancel")}
        </button>
      </div>

      {busy && (
        // Two phases and about twenty seconds, so the wait is named rather
        // than left as a spinner over a video that hasn't changed yet.
        <p className="text-[11px] text-white/30">
          {t("wait")}
        </p>
      )}
    </div>
  );
}
