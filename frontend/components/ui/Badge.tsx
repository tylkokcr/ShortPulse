import { type HTMLAttributes } from "react";
import clsx from "clsx";

type Tone = "neutral" | "accent" | "pulse";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-border bg-white/5 text-white/60",
  accent: "border-accent/30 bg-accent/10 text-accent",
  pulse: "border-pulse/30 bg-pulse/10 text-pulse",
};

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wide",
        TONE_CLASSES[tone],
        className
      )}
      {...props}
    />
  );
}
