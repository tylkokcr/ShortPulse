"use client";

import { useState } from "react";
import { Check, ThumbsDown } from "lucide-react";
import clsx from "clsx";
import type { SceneFeedback as Verdict } from "@/lib/types";

/**
 * Saying a scene came out wrong, next to the button that fixes it.
 *
 * The placement is the whole idea. A complaint form somewhere else asks a
 * user to describe a problem and then leaves them with it; here the same
 * row offers a re-roll, so the answer to "this is wrong" is "then draw it
 * again" rather than "thank you for your feedback".
 *
 * Thumbs-down only, deliberately. Nobody thumbs up eight scenes, and a
 * control that asks them to is noise on every row for a signal that
 * arrives once. The verdict on the video as a whole is where "good" gets
 * recorded — see VideoFeedback.
 *
 * A reason is one tap from a fixed list because the useful question is
 * "how often is it the visual", which is a query only if the answer is
 * countable. The free-text box is there for the case the list didn't
 * anticipate, which is also the case worth reading.
 */
const REASONS: { id: string; label: string }[] = [
  { id: "visual", label: "The picture" },
  { id: "match", label: "Doesn't match the line" },
  { id: "voice", label: "Voice" },
  { id: "captions", label: "Captions" },
  { id: "pacing", label: "Too fast / slow" },
  { id: "other", label: "Something else" },
];

export function SceneFeedback({
  index,
  verdict,
  canReRoll,
  onSubmit,
}: {
  index: number;
  /** This viewer's existing verdict on this scene, if they left one. */
  verdict?: Verdict;
  /** Whether a re-roll control is actually rendered under this one.
   *  False for anything rendered before the working files were kept, and
   *  the hint below must not promise a button that isn't there. */
  canReRoll: boolean;
  onSubmit: (index: number, reason: string, note: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(verdict?.reason ?? "");
  const [note, setNote] = useState(verdict?.note ?? "");
  const [saving, setSaving] = useState(false);

  const flagged = verdict?.rating === "down";

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={clsx(
          "flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[10px] transition-colors",
          flagged
            ? "border-amber-500/40 bg-amber-500/10 text-amber-300/80"
            : "border-border text-white/40 hover:border-border-strong hover:text-white/70"
        )}
      >
        <ThumbsDown size={11} />
        {flagged ? "flagged" : "wrong?"}
      </button>
    );
  }

  return (
    <div className="flex w-full flex-col gap-2 rounded-lg border border-border bg-background p-3">
      <span className="font-mono text-[10px] uppercase tracking-widest text-white/30">
        what&apos;s wrong with this one?
      </span>

      <div className="flex flex-wrap gap-1.5">
        {REASONS.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setReason(r.id)}
            className={clsx(
              "rounded-md border px-2 py-1 text-[11px] transition-colors",
              reason === r.id
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-border text-white/50 hover:border-border-strong hover:text-white/80"
            )}
          >
            {r.label}
          </button>
        ))}
      </div>

      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        maxLength={1000}
        placeholder="Anything else? (optional)"
        className="resize-none rounded-md border border-border bg-surface px-2 py-1.5 text-xs leading-relaxed outline-none focus:border-border-strong"
      />

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={saving || !reason}
          onClick={async () => {
            setSaving(true);
            try {
              await onSubmit(index, reason, note.trim());
              setOpen(false);
            } finally {
              setSaving(false);
            }
          }}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs text-white/80 transition-colors hover:border-border-strong disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Check size={12} />
          {saving ? "Saving…" : "Send"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-md px-2 py-1.5 text-xs text-white/40 transition-colors hover:text-white/70"
        >
          Cancel
        </button>
        {/* Said here rather than after sending, because it is the reason
            to bother: the fix is the control immediately below this one.
            Only when there is one — an older render has no working files
            left to re-draw from, and pointing at a button that isn't
            there is worse than staying quiet. */}
        {canReRoll && (
          <span className="ml-auto text-[11px] text-white/25">
            Then re-roll it below
          </span>
        )}
      </div>
    </div>
  );
}
