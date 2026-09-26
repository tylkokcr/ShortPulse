"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";
import { AppRail } from "@/components/layout/AppRail";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { AccountBar } from "@/components/auth/AccountBar";
import { GridBackdrop } from "@/components/ui/GridBackdrop";

/**
 * The frame every signed-in screen sits in.
 *
 * One rail, one bar, one content width. Before this each page drew its
 * own: five screens with four different max-widths and a backdrop that
 * appeared on one of them, so moving between them shifted the column
 * sideways and changed the background. That reads as a set of pages
 * rather than an application, and it is the whole of the difference.
 *
 * Two layouts, not one responsive one. At `lg` and up the rail is
 * permanent and the content scrolls inside its own pane against a fixed
 * frame — the thing that makes an app feel like an app rather than a
 * document. Below it the rail is gone, SiteHeader and its MobileNav carry
 * the links exactly as they did, and the page scrolls normally: a phone
 * has neither the width for a rail nor any use for a pane that scrolls
 * inside a viewport the browser chrome is already resizing.
 */
export function AppShell({
  section,
  children,
  /** Widened past the default only where the content is a grid that
   *  genuinely needs it — the library's cards. Everything else takes the
   *  one width, which is the point. */
  wide = false,
  actions,
  aside,
  asideOpen = false,
  footer,
}: {
  /** A key under `nav`, not a label. The rail names these four screens
   *  from the catalogue; passing a literal here printed "Library" next to
   *  a rail reading "Kütüphane". */
  section: "studio" | "library" | "connections" | "credits" | "project";
  children: React.ReactNode;
  wide?: boolean;
  actions?: React.ReactNode;
  /** A panel beside the content rather than over it, because the
   *  studio's settings sit next to a live preview of the caption style
   *  and the aspect ratio — the two things most of those settings
   *  change, so a drawer that covered it would hide the answer to the
   *  question it was opened to ask.
   *
   *  It positions itself; what the shell does is get out of its way. */
  aside?: React.ReactNode;
  /** Whether that panel is showing, so the content can make room for it.
   *
   *  A margin rather than sizing the panel as a flex sibling. The flex
   *  version read better in the source and would not lay out: the item
   *  computed to zero width beside a `flex-1` column that had taken the
   *  whole row, and stayed at zero through an inline `width: 400px
   *  !important`. A margin is not a negotiation. */
  asideOpen?: boolean;
  /** A bar pinned under the content. Fixed to the window below `lg` as it
   *  always was, and in flow at `lg` — where the pane no longer spans the
   *  window, so a fixed bar ran under the rail on one side and under the
   *  settings panel on the other, putting the button that spends credits
   *  behind a panel. */
  footer?: React.ReactNode;
}) {
  const t = useTranslations("nav");

  return (
    <div className="relative lg:flex lg:h-dvh lg:overflow-hidden">
      {/* The same drafting surface the landing and the auth pages sit on,
          quieter. It lived only on the pages a visitor sees once, which
          left the two screens people actually work in — this one and the
          library — on flat #0a0a0a. Fixed and behind everything, so the
          rail's own background covers it on the left and the content area
          gets the grid. */}
      <GridBackdrop intensity="ambient" />

      <AppRail />

      {/* Below lg only. The rail replaces it above, and rendering both
          would put the same four links on screen twice. */}
      <div className="lg:hidden">
        <SiteHeader right={<AccountBar />} showLibrary />
      </div>

      <div
        className={clsx(
          "flex min-w-0 flex-1 flex-col",
          "aside:transition-[margin] aside:duration-300",
          // Only where the arithmetic works. Below `aside` the panel is
          // a sheet over the page instead, because a 400px column taken
          // out of 1024 leaves 48px of form and a page that scrolls
          // sideways — see the breakpoint's own note.
          asideOpen && "aside:mr-[400px]"
        )}
      >
        {/* The section name lives here rather than in each page's body,
            where it used to be an eyebrow above the heading. The frame
            owns the chrome; the page owns the sentence. */}
        <header className="hidden shrink-0 items-center gap-4 border-b border-border/60 px-8 py-3.5 lg:flex">
          <span className="font-mono text-xs uppercase tracking-widest text-white/40">
            {t(section)}
          </span>
          <div className="ml-auto flex items-center gap-4">
            {actions}
            <AccountBar compact />
          </div>
        </header>

        <main className="flex-1 lg:overflow-y-auto">
          <div
            className={clsx(
              "mx-auto w-full px-6 pb-24 pt-8 lg:px-8",
              wide ? "max-w-6xl" : "max-w-5xl"
            )}
          >
            {children}
          </div>
        </main>

        {footer && (
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border/60 bg-background/85 backdrop-blur-md lg:static lg:z-auto lg:shrink-0">
            {footer}
          </div>
        )}
      </div>

      {aside}
    </div>
  );
}
