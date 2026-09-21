"use client";

import clsx from "clsx";
import { AppRail } from "@/components/layout/AppRail";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { AccountBar } from "@/components/auth/AccountBar";

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
}: {
  section: string;
  children: React.ReactNode;
  wide?: boolean;
  actions?: React.ReactNode;
}) {
  return (
    <div className="relative lg:flex lg:h-dvh lg:overflow-hidden">
      <AppRail />

      {/* Below lg only. The rail replaces it above, and rendering both
          would put the same four links on screen twice. */}
      <div className="lg:hidden">
        <SiteHeader right={<AccountBar />} showLibrary />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* The section name lives here rather than in each page's body,
            where it used to be an eyebrow above the heading. The frame
            owns the chrome; the page owns the sentence. */}
        <header className="hidden shrink-0 items-center gap-4 border-b border-border/60 px-8 py-3.5 lg:flex">
          <span className="font-mono text-xs uppercase tracking-widest text-white/40">
            {section}
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
      </div>
    </div>
  );
}
