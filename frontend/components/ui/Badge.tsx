import { type HTMLAttributes } from "react";
import clsx from "clsx";

type Tone = "neutral" | "accent" | "live";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-border bg-white/5 text-white/60",
  accent: "border-accent/40 bg-accent/10 text-accent",
  live: "border-live/40 bg-live/10 text-live",
};

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em]",
        TONE_CLASSES[tone],
        className
      )}
      {...props}
    />
  );
}
