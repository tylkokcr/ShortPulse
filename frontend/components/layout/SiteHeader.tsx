import Link from "next/link";
import { Github, Library } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

const REPO_URL = "https://github.com/tylkokcr/ShortPulse";

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
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/75 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
        <Link href="/" className="transition-opacity hover:opacity-80">
          <Logo />
        </Link>
        <div className="flex items-center gap-5">
          {showLibrary && (
            <Link
              href="/library"
              className="hidden items-center gap-1.5 text-sm text-white/50 transition-colors hover:text-white sm:flex"
            >
              <Library size={16} />
              Library
            </Link>
          )}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-1.5 text-sm text-white/50 transition-colors hover:text-white sm:flex"
          >
            <Github size={16} />
            Source
          </a>
          {right}
        </div>
      </div>
    </header>
  );
}
