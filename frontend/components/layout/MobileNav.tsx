"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Github, Library, Menu, Share2, X } from "lucide-react";
import clsx from "clsx";
import { AccentSwitcher } from "@/components/ui/AccentSwitcher";
import { getSocialPlatforms } from "@/lib/api";

/**
 * The header's links, on a phone.
 *
 * They used to be `hidden sm:flex` and nothing replaced them, so on a
 * phone there was no route to the library or to the connected accounts at
 * all — the pages existed and could not be reached. The header genuinely
 * has no room for four links at 390px; what it has room for is one
 * button.
 *
 * Deliberately a panel under the bar rather than a full-screen overlay:
 * this is four links, and covering the whole screen to show four links
 * asks the user to dismiss something before they can see where they were.
 */
export function MobileNav({ showLibrary }: { showLibrary: boolean }) {
  const [open, setOpen] = useState(false);
  const [publishes, setPublishes] = useState(false);

  useEffect(() => {
    if (!showLibrary) return;
    let live = true;
    getSocialPlatforms()
      .then((platforms) => live && setPublishes(platforms.length > 0))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [showLibrary]);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return (
    <div className="sm:hidden">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        // 40px square: the smallest target that is still comfortable with
        // a thumb, and the same height as the account bar beside it.
        className="flex h-10 w-10 items-center justify-center rounded-lg text-white/60 transition-colors hover:bg-white/5 hover:text-white"
      >
        {open ? <X size={18} /> : <Menu size={18} />}
      </button>

      {open && (
        <>
          {/* Catches the tap that means "I'm done", which on a panel this
              small is usually a tap on the page rather than on the X. */}
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            onClick={() => setOpen(false)}
            // z-30 rather than a hardcoded offset for the header's
            // height: the bar is z-40, so it stays above this and the
            // dim lands only on the page.
            className="fixed inset-0 z-30 cursor-default bg-background/60"
          />
          <nav className="absolute inset-x-0 top-full z-40 border-b border-border bg-background">
            <div className="flex flex-col px-6 py-2">
              {/* Closed on the tap rather than on the route change: the
                  header outlives the navigation, and tapping the page you
                  are already on changes no route at all. */}
              {showLibrary && (
                <MobileLink
                  href="/library"
                  icon={Library}
                  label="Library"
                  onNavigate={() => setOpen(false)}
                />
              )}
              {showLibrary && publishes && (
                <MobileLink
                  href="/connections"
                  icon={Share2}
                  label="Connections"
                  onNavigate={() => setOpen(false)}
                />
              )}
              <a
                href="https://github.com/tylkokcr/ShortPulse"
                target="_blank"
                rel="noreferrer"
                className={MOBILE_LINK}
              >
                <Github size={17} className="shrink-0 text-white/40" />
                Source
              </a>
              <div className="flex items-center justify-between border-t border-border/60 py-4">
                <span className="text-sm text-white/40">Accent</span>
                <AccentSwitcher />
              </div>
            </div>
          </nav>
        </>
      )}
    </div>
  );
}

// py-4 rather than py-2: rows a thumb can hit without aiming, which is
// most of the difference between a menu that works standing up and one
// that does not.
const MOBILE_LINK =
  "flex items-center gap-3 border-b border-border/60 py-4 text-sm text-white/80 transition-colors hover:text-white";

function MobileLink({
  href,
  icon: Icon,
  label,
  onNavigate,
}: {
  href: string;
  icon: typeof Library;
  label: string;
  onNavigate: () => void;
}) {
  return (
    <Link href={href} onClick={onNavigate} className={clsx(MOBILE_LINK)}>
      <Icon size={17} className="shrink-0 text-white/40" />
      {label}
    </Link>
  );
}
