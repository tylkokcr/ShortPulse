"use client";

import { useEffect, useState } from "react";
import { Coins, Github, Library, LogOut, Share2, Wand2 } from "lucide-react";
import clsx from "clsx";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { Logo } from "@/components/ui/Logo";
import { AccentSwitcher } from "@/components/ui/AccentSwitcher";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { getSocialPlatforms } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { useAuth } from "@/components/auth/AuthProvider";

const REPO_URL = "https://github.com/tylkokcr/ShortPulse";

/**
 * Where you are in the app, and everywhere else you could be.
 *
 * The signed-in screens used to be five pages that each drew their own
 * frame, and they did not agree on one: the content column was 5xl in the
 * studio, 6xl in the library, 4xl on a project, 3xl on connections. Moving
 * between them shifted the whole page sideways, which is the difference
 * between a product and a set of pages — an application has one frame and
 * changes what is inside it.
 *
 * Labels, not bare icons. The rail costs 208px of a wide screen, and what
 * that buys is not having to hover four glyphs to find out where they go.
 * Below `lg` it is gone entirely and MobileNav carries the same links, for
 * the same reason it always did: a phone does not have 208px to spare.
 */
export function AppRail() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const { session, enabled, signOut } = useAuth();
  const credits = useShortPulseStore((s) => s.credits);

  // Same rule the header's link follows: a deployment that publishes
  // nowhere does not advertise a page that leads to an empty list.
  const [publishes, setPublishes] = useState(false);
  useEffect(() => {
    let live = true;
    getSocialPlatforms()
      .then((platforms) => live && setPublishes(platforms.length > 0))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const items = [
    { href: "/", icon: Wand2, label: t("studio") },
    { href: "/library", icon: Library, label: t("library") },
    ...(publishes ? [{ href: "/connections", icon: Share2, label: t("connections") }] : []),
    ...(credits?.enabled ? [{ href: "/credits", icon: Coins, label: t("credits") }] : []),
  ];

  return (
    <nav className="hidden w-52 shrink-0 flex-col border-r border-border/60 bg-surface/30 lg:flex">
      <div className="px-4 py-4">
        <Link href="/" className="inline-flex transition-opacity hover:opacity-80">
          <Logo />
        </Link>
      </div>

      <div className="flex flex-col gap-0.5 px-2">
        {items.map((item) => {
          // Exact match for the studio, prefix for the rest: "/" is a
          // prefix of everything, and a rail that marks every page as the
          // studio marks nothing.
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={clsx(
                "relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm",
                "transition-[color,background-color] duration-200",
                active
                  ? "bg-accent/[0.08] text-white"
                  : "text-white/50 hover:bg-surface-hover hover:text-white/80"
              )}
            >
              {/* A bar on the rail rather than a filled pill: the fill
                  alone read as a hover state that had got stuck. */}
              <span
                aria-hidden
                className={clsx(
                  "absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-r transition-colors duration-200",
                  active ? "bg-accent" : "bg-transparent"
                )}
              />
              <item.icon size={15} className={active ? "text-accent" : undefined} />
              {item.label}
            </Link>
          );
        })}
      </div>

      {/* Pushed to the bottom: preferences and identity are things you
          reach for occasionally, and putting them under the destinations
          would give them the same weight as the four screens. */}
      <div className="mt-auto flex flex-col gap-3 border-t border-border/60 px-4 py-4">
        <div className="flex items-center justify-between gap-2">
          <LanguageSwitcher />
          <AccentSwitcher />
        </div>

        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 text-xs text-white/35 transition-colors hover:text-white/70"
        >
          <Github size={13} />
          {t("source")}
        </a>

        {enabled && session && (
          <div className="flex flex-col gap-1.5 border-t border-border/60 pt-3">
            <span className="truncate text-[11px] text-white/30" title={session.user.email}>
              {session.user.email}
            </span>
            <button
              onClick={signOut}
              className="flex items-center gap-1.5 text-xs text-white/40 transition-colors hover:text-white/80"
            >
              <LogOut size={12} />
              {t("signOut")}
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
