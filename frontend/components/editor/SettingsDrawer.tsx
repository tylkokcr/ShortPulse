"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { X } from "lucide-react";
import clsx from "clsx";

/**
 * The studio's settings, beside the page rather than below it.
 *
 * The form used to be five stacked accordions and the page was 2900px
 * tall — nearly four screens for one decision each. Everything past "the
 * idea" is a refinement with a working default, so it belongs somewhere
 * you open, not somewhere you scroll past.
 *
 * The panel is fixed to the window and slides in. Past the `aside`
 * breakpoint the shell gives the content column a matching right margin,
 * so the page moves aside rather than being covered — which matters
 * because the caption and format preview is the thing most of these
 * settings change, and hiding it would hide the answer to the question
 * the panel was opened to ask.
 *
 * Below that it is a sheet with a backdrop, because there is no room to
 * be anything else. Keeping the push-aside down to `lg` was the bug this
 * breakpoint exists to fix: three columns competing for 1024px left the
 * form at 275px — narrower than the 400px panel that displaced it — and
 * the page scrolling sideways by 203px. One focus surface at a time is
 * the honest answer at that width, and it is what the flow already did
 * on a phone.
 */
export function SettingsDrawer({
  open,
  onClose,
  icon: Icon,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  const t = useTranslations("studio.drawer");
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {/* Below `aside` only: past that the panel takes width instead of
          covering anything, so there is nothing to dim and nothing
          behind it that a click should dismiss. */}
      <div
        aria-hidden
        onClick={onClose}
        className={clsx(
          "fixed inset-0 z-40 bg-black/60 transition-opacity duration-300 aside:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
      />

      {/* Pinned to the window and slid in, at every width. What changes
          at `aside` is what the page does about it: there the content
          column takes a matching right margin and moves aside, so the
          panel sits next to the preview instead of on top of it. Below
          that it covers the preview — deliberately, since the preview is
          the first thing worth giving up when only one of the two can be
          full width. */}
      <div
        className={clsx(
          "fixed inset-y-0 right-0 z-50 w-full max-w-sm transition-transform duration-300",
          "aside:max-w-none aside:w-[400px]",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div
          role="dialog"
          aria-modal="false"
          aria-label={title}
          className="flex h-full w-full flex-col border-l border-border bg-surface/95 backdrop-blur-sm"
        >
          <div className="flex shrink-0 items-center gap-2 border-b border-border/60 px-5 py-3.5">
            {Icon && <Icon size={14} className="text-accent" />}
            <h2 className="text-sm font-semibold text-white/80">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label={t("close")}
              className="ml-auto rounded-lg p-1.5 text-white/40 transition-colors hover:bg-surface-hover hover:text-white"
            >
              <X size={15} />
            </button>
          </div>

          {/* Its own scroll, so a long settings list never moves the page
              behind it. */}
          <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-5 py-5">{children}</div>
        </div>
      </div>
    </>
  );
}
