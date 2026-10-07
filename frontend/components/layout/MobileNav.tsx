"use client";

import { useEffect, useState } from "react";
import { Coins, Github, Library, Menu, Share2, Wand2, X } from "lucide-react";
import clsx from "clsx";
import { useTranslations } from "next-intl";
import { AccentSwitcher } from "@/components/ui/AccentSwitcher";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { Link, usePathname } from "@/i18n/navigation";
import { useShortPulseStore } from "@/lib/store";
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
  const t = useTranslations("nav");
  const pathname = usePathname();
  const creditsOn = useShortPulseStore((s) => s.credits?.enabled ?? false);
  // Exact for the studio, prefix for the rest — "/" prefixes everything.
  const here = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

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
        aria-label={open ? t("closeMenu") : t("openMenu")}
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
              {/* Every place the desktop rail goes. The studio and credits
                  were missing, so on a phone the only way back to making
                  a video was the logo, and credits had no way in at all. */}
              {showLibrary && (
                <MobileLink
                  href="/"
                  icon={Wand2}
                  label={t("studio")}
                  active={here("/")}
                  onNavigate={() => setOpen(false)}
                />
              )}
              {showLibrary && (
                <MobileLink
                  href="/library"
                  icon={Library}
                  label={t("library")}
                  active={here("/library")}
                  onNavigate={() => setOpen(false)}
                />
              )}
              {showLibrary && publishes && (
                <MobileLink
                  href="/connections"
                  icon={Share2}
                  label={t("connections")}
                  active={here("/connections")}
                  onNavigate={() => setOpen(false)}
                />
              )}
              {showLibrary && creditsOn && (
                <MobileLink
                  href="/credits"
                  icon={Coins}
                  label={t("credits")}
                  active={here("/credits")}
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
                {t("source")}
              </a>
              <div className="flex items-center justify-between border-b border-border/60 py-3">
                <span className="text-sm text-white/40">{t("language")}</span>
                <LanguageSwitcher />
              </div>
              <div className="flex items-center justify-between py-4">
                <span className="text-sm text-white/40">{t("accent")}</span>
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
  active = false,
  onNavigate,
}: {
  href: string;
  icon: typeof Library;
  label: string;
  active?: boolean;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={clsx(MOBILE_LINK, active && "text-white")}
    >
      <Icon size={17} className={clsx("shrink-0", active ? "text-accent" : "text-white/40")} />
      {label}
    </Link>
  );
}
