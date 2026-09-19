import { useTranslations } from "next-intl";
import { Github, Library } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Logo } from "@/components/ui/Logo";
import { AccentSwitcher } from "@/components/ui/AccentSwitcher";
import { ConnectionsLink } from "@/components/layout/ConnectionsLink";
import { MobileNav } from "@/components/layout/MobileNav";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";

const REPO_URL = "https://github.com/tylkokcr/ShortPulse";

// Shared by every item in the bar. Hidden below `sm`, where the header is
// at its width budget — MobileNav carries the same links behind one
// button there, which it did not always, and for a while a phone simply
// had no way to reach them.
const NAV_LINK =
  "hidden items-center gap-1.5 text-sm text-white/50 transition-colors hover:text-white sm:flex";

/**
 * Shared top bar for every screen — marketing, studio and project pages.
 * `right` is a slot so each page can drop in whatever's contextually
 * relevant (a "Sign in" CTA on the landing page, the account/credits bar
 * once signed in) without this component knowing about auth state.
 */
export function SiteHeader({
  right,
  showLibrary = false,
}: {
  right?: React.ReactNode;
  /** Off by default: the marketing page has no library to link to, and
   *  offering one to a signed-out visitor leads straight to a login wall. */
  showLibrary?: boolean;
}) {
  const t = useTranslations("nav");

  return (
    // `relative` so the mobile panel can hang off the bar rather than off
    // the page, which is what keeps it under the header when the page is
    // scrolled.
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/75 backdrop-blur-md">
      <div className="relative mx-auto flex max-w-6xl items-center justify-between gap-3 px-6 py-4 sm:gap-4">
        <Link href="/" className="transition-opacity hover:opacity-80">
          <Logo />
        </Link>
        <div className="flex items-center gap-5">
          {showLibrary && (
            <>
              <Link href="/library" className={NAV_LINK}>
                <Library size={16} />
                {t("library")}
              </Link>
              <ConnectionsLink className={NAV_LINK} />
            </>
          )}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className={NAV_LINK}
          >
            <Github size={16} />
            {t("source")}
          </a>
          {/* Hidden on small screens: five dots is a lot of tap targets to
              spend on a phone header, and the choice is a preference rather
              than a control anyone needs on the way to a render. */}
          <LanguageSwitcher className="hidden sm:flex" />
          <AccentSwitcher className="hidden md:flex" />
          {right}
          <MobileNav showLibrary={showLibrary} />
        </div>
      </div>
    </header>
  );
}
