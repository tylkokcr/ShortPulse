"use client";

import { useEffect, useRef } from "react";
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
 * The panel is fixed to the window and slides in. At `lg` the shell
 * gives the content column a matching right margin, so the page moves
 * aside rather than being covered — which matters because the caption
 * and format preview is the thing most of these settings change, and
 * hiding it would hide the answer to the question the panel was opened
 * to ask. Below `lg` that preview is stacked out of view anyway, so it
 * is a plain overlay with a backdrop.
 */
export function SettingsDrawer({
  open,
  onClose,
  title,
  scrollTo,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Id of the group to land on. */
  scrollTo?: string | null;
  children: React.ReactNode;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Set scrollTop from the target's own offset rather than calling
  // scrollIntoView. The panel opens by animating its width from zero over
  // 300ms, so anything that reads layout has to either wait out the
  // animation or not depend on it — and waiting on a duration is a race
  // that loses on a slow frame. It does not need to: the inner column is
  // a fixed 400px whatever the outer one is doing, so offsetTop is
  // already the right number on the first frame.
  //
  // The browser clamps this to the end of the scroll range, so a group
  // near the bottom lands partway down the panel rather than at its top.
  // That is the right answer rather than something to pad around: there
  // is nothing below it to scroll up, and every group is short enough to
  // be wholly on screen from there.
  useEffect(() => {
    const container = scrollRef.current;
    if (!open || !scrollTo || !container) return;
    const target = container.querySelector<HTMLElement>(`#${CSS.escape(scrollTo)}`);
    if (target) container.scrollTop = target.offsetTop;
  }, [open, scrollTo]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {/* Below lg only: at lg the panel takes width instead of covering
          anything, so there is nothing to dim and nothing behind it that
          a click should dismiss. */}
      <div
        aria-hidden
        onClick={onClose}
        className={clsx(
          "fixed inset-0 z-40 bg-black/60 transition-opacity duration-300 lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
      />

      {/* Pinned to the window and slid in, at every width. What changes
          at `lg` is what the page does about it: there the content column
          takes a matching right margin and moves aside, so the panel sits
          next to the preview instead of on top of it. Below `lg` the
          preview is stacked out of view anyway and this is a plain
          overlay. */}
      <div
        className={clsx(
          "fixed inset-y-0 right-0 z-50 w-full max-w-sm transition-transform duration-300",
          "lg:max-w-none lg:w-[400px]",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div
          role="dialog"
          aria-modal="false"
          aria-label={title}
          className="flex h-full w-full flex-col border-l border-border bg-surface/95 backdrop-blur-sm"
        >
          <div className="flex shrink-0 items-center gap-3 border-b border-border/60 px-5 py-3.5">
            <h2 className="text-sm font-semibold text-white/80">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="ml-auto rounded-lg p-1.5 text-white/40 transition-colors hover:bg-surface-hover hover:text-white"
            >
              <X size={15} />
            </button>
          </div>

          {/* Its own scroll, so a long settings list never moves the page
              behind it. */}
          <div ref={scrollRef} className="relative flex-1 overflow-y-auto px-5 py-5">
            {children}
          </div>
        </div>
      </div>
    </>
  );
}

/**
 * One group inside the drawer.
 *
 * Flat, with a heading, rather than another accordion: the drawer is
 * already the thing that was hiding these, and hiding them twice would
 * make a two-click job of picking a voice.
 */
export function DrawerGroup({
  id,
  icon: Icon,
  title,
  children,
}: {
  id: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-4 border-b border-border/60 pb-6 last:border-0 last:pb-0">
      <div className="mb-4 flex items-center gap-2">
        <Icon size={14} className="text-accent" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="flex flex-col gap-5">{children}</div>
    </section>
  );
}
