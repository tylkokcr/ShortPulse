"use client";

import { useEffect, useState } from "react";
import { Coins, Github, Library, LogOut, PanelLeftClose, PanelLeftOpen, Share2, Wand2 } from "lucide-react";
import clsx from "clsx";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { Logo } from "@/components/ui/Logo";
import { AccentSwitcher } from "@/components/ui/AccentSwitcher";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { getSocialPlatforms } from "@/lib/api";
import { RAIL_STORAGE_KEY } from "@/components/layout/railBoot";
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

  // Mirrors the attribute the boot script wrote, so the button can say
  // which way it goes. The attribute is the truth; this is a label.
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    setCollapsed(document.documentElement.getAttribute("data-rail") === "collapsed");
  }, []);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    const root = document.documentElement;
    if (next) root.setAttribute("data-rail", "collapsed");
    else root.removeAttribute("data-rail");
    try {
      localStorage.setItem(RAIL_STORAGE_KEY, next ? "collapsed" : "open");
    } catch {
      // Private windows throw. The rail still collapses for this page.
    }
  }
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
    <nav
      // No fill. The rail used to be a 30% surface wash, which was there
      // to separate it from a flat black page — and now the page has a
      // drafting surface of its own, that wash only dimmed the grid under
      // one column of it. The hairline does the separating; the surface
      // runs edge to edge behind everything, which is what makes it read
      // as one sheet rather than a panel beside a panel.
      className="app-rail hidden shrink-0 flex-col overflow-hidden border-r border-border/50 lg:flex"
    >
      <div className="flex items-center gap-2 px-4 py-4">
        <Link href="/" className="inline-flex shrink-0 transition-opacity hover:opacity-80">
          <Logo />
        </Link>
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? t("expandRail") : t("collapseRail")}
          title={collapsed ? t("expandRail") : t("collapseRail")}
          className="rail-label ml-auto shrink-0 rounded-md p-1 text-white/30 transition-colors hover:bg-surface-hover hover:text-white/70"
        >
          <PanelLeftClose size={15} />
        </button>
      </div>

      {/* Its own row when collapsed: there is no logo beside it to sit
          next to, and a 64px column has no "ml-auto" worth having. */}
      {collapsed && (
        <button
          type="button"
          onClick={toggle}
          aria-label={t("expandRail")}
          title={t("expandRail")}
          className="mx-auto mb-1 rounded-md p-1.5 text-white/30 transition-colors hover:bg-surface-hover hover:text-white/70"
        >
          <PanelLeftOpen size={15} />
        </button>
      )}

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
              title={item.label}
              className={clsx(
                "rail-item relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm",
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
              <item.icon size={15} className={clsx("shrink-0", active && "text-accent")} />
              <span className="rail-label">{item.label}</span>
            </Link>
          );
        })}
      </div>

      {/* Pushed to the bottom: preferences and identity are things you
          reach for occasionally, and putting them under the destinations
          would give them the same weight as the four screens. */}
      <div className="rail-foot mt-auto flex flex-col gap-3 border-t border-border/60 px-4 py-4">
        {/* Stacked, not side by side. A language name and five accent
            dots come to 192px of controls in 176px of rail, and the last
            dot was cut off by the border. */}
        <LanguageSwitcher className="-ml-2" />
        <AccentSwitcher />

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
