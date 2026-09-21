import clsx from "clsx";

/**
 * The pulse/waveform mark, shared by the header, landing hero and favicon
 * (app/icon.svg). Kept as inline SVG rather than an <img> so it can inherit
 * currentColor contexts and stay crisp at any size.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={clsx("shrink-0", className)} aria-hidden>
      {/* Square, not a rounded app-store tile, and a flat accent rather
          than the old violet-to-teal ramp — the mark was the most visible
          piece of the generated-template palette. */}
      <rect width="32" height="32" rx="3" className="fill-surface stroke-border" strokeWidth="1" />
      <path
        d="M4 17h5l2.5-7L15 24l3-14 2 7h8"
        className="stroke-accent"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2 font-semibold tracking-[-0.01em]", className)}>
      <LogoMark className="h-7 w-7" />
      {/* Carries the same class the rail's other labels do, so a
          collapsed rail keeps the mark and drops the word without this
          component needing to know a rail exists. */}
      <span className="rail-label">ShortPulse</span>
    </span>
  );
}
