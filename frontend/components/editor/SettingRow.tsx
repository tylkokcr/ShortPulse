"use client";

import { ChevronRight } from "lucide-react";
import clsx from "clsx";

/**
 * A setting group, as a line rather than a panel.
 *
 * Says what it is currently set to and opens the drawer at it. The
 * summary is the point: four of these stack into the height one closed
 * accordion used to take, and you can read the whole configuration
 * without opening anything.
 *
 * Shared by both studio tabs. The caption flow was still one long column
 * of expanded controls — 2238px, three screens — while the generate flow
 * beside it had been rows-and-a-drawer for months. Two tabs of the same
 * screen disagreeing about how settings work is the kind of thing a user
 * reads as two different products.
 */
export function SettingRow({
  icon: Icon,
  title,
  summary,
  open,
  onClick,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  summary: string;
  open: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      className={clsx(
        "group flex items-center gap-3 rounded-lg border px-4 py-3 text-left",
        "transition-[border-color,background-color] duration-200",
        open
          ? "border-accent/50 bg-accent/[0.06]"
          : "border-border hover:border-border-strong hover:bg-surface-hover"
      )}
    >
      <Icon size={14} className={clsx("shrink-0", open ? "text-accent" : "text-white/40")} />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{title}</span>
        <span className="mt-0.5 block truncate text-xs text-white/40">{summary}</span>
      </span>
      <ChevronRight
        size={15}
        className={clsx(
          "shrink-0 transition-colors",
          open ? "text-accent" : "text-white/25 group-hover:text-white/50"
        )}
      />
    </button>
  );
}
