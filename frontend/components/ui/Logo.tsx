import clsx from "clsx";

/**
 * The pulse/waveform mark, shared by the header, landing hero and favicon
 * (app/icon.svg). Kept as inline SVG rather than an <img> so it can inherit
 * currentColor contexts and stay crisp at any size.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={clsx("shrink-0", className)} aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-surface" />
      <path
        d="M4 17h5l2.5-7L15 24l3-14 2 7h8"
        stroke="url(#logo-gradient)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <defs>
        <linearGradient id="logo-gradient" x1="4" y1="16" x2="28" y2="16" gradientUnits="userSpaceOnUse">
          <stop stopColor="#7c5cff" />
          <stop offset="1" stopColor="#2dd4bf" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <LogoMark className="h-7 w-7" />
      ShortPulse
    </span>
  );
}
