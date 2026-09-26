"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";

/**
 * A field that states what it is set to, and opens when you disagree.
 *
 * The audio panel was two labels with a full catalogue under each — every
 * voice for the language and every music track, always expanded, 1676px
 * of panel for two decisions that already had answers. Nobody scrolls two
 * screens to confirm a default.
 *
 * So the value comes first and the catalogue is behind it. Closed, this is
 * one row; open, it is exactly what it was before. Nothing is hidden that
 * was not already an answer the user had.
 *
 * Deliberately not `<details>`: the summary row wants the same chevron,
 * hover and focus treatment as every other row in this app, and a
 * `<details>` marker fights all three across browsers for one saved line
 * of state.
 */
export function FieldDisclosure({
  label,
  value,
  children,
  className,
}: {
  label: string;
  /** What it is set to right now, shown while closed. */
  value: string;
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className={clsx("flex flex-col", className)}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5 text-left transition-colors duration-200 hover:border-border-strong hover:bg-surface-hover"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-medium text-white/70">{label}</span>
          <span className="mt-0.5 block truncate text-[11px] text-white/40">{value}</span>
        </span>
        <ChevronDown
          size={14}
          className={clsx(
            "shrink-0 text-white/30 transition-transform duration-200",
            open && "rotate-180"
          )}
        />
      </button>

      {/* Mounted only while open. The voice list fetches its catalogue on
          mount and the music list its tracks, so rendering both closed
          would spend two requests on panels nobody opened. */}
      {open && <div className="pt-3">{children}</div>}
    </div>
  );
}
