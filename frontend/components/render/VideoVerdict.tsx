"use client";

import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useTranslations } from "next-intl";
import clsx from "clsx";
import type { SceneFeedback as Verdict } from "@/lib/types";

/**
 * Did this one come out well?
 *
 * The counterpart to the per-scene flags, and the reason they mean
 * anything: without a "this was fine" the table only ever fills with
 * complaints, and three of them could be three bad renders out of three
 * or out of three hundred. One number is not a rate.
 *
 * Both directions here, unlike a scene row — this is asked once per
 * video, so a thumbs-up costs one click rather than one per scene. And it
 * is asked after the video exists and can be watched, not while it is
 * being waited for.
 */
export function VideoVerdict({
  verdict,
  onSubmit,
}: {
  verdict?: Verdict;
  onSubmit: (rating: "up" | "down") => Promise<void>;
}) {
  const t = useTranslations("app.feedback");
  const [saving, setSaving] = useState<"up" | "down" | null>(null);
  const answered = verdict?.rating;

  async function send(rating: "up" | "down") {
    setSaving(rating);
    try {
      await onSubmit(rating);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="flex items-center gap-3 border-t border-border pt-3">
      <span className="text-[11px] text-white/35">
        {answered ? t("videoThanks") : t("videoAsk")}
      </span>

      <div className="ml-auto flex items-center gap-1.5">
        {(["up", "down"] as const).map((rating) => {
          const Icon = rating === "up" ? ThumbsUp : ThumbsDown;
          const on = answered === rating;
          return (
            <button
              key={rating}
              type="button"
              disabled={saving !== null}
              onClick={() => send(rating)}
              aria-label={rating === "up" ? t("videoUp") : t("videoDown")}
              aria-pressed={on}
              className={clsx(
                "flex h-7 w-7 items-center justify-center rounded-md border transition-colors disabled:opacity-40",
                on
                  ? rating === "up"
                    ? "border-accent/50 bg-accent/10 text-accent"
                    : "border-amber-500/40 bg-amber-500/10 text-amber-300/80"
                  : "border-border text-white/35 hover:border-border-strong hover:text-white/70"
              )}
            >
              <Icon size={13} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
