"use client";

import { useTransition } from "react";
import { Globe } from "lucide-react";
import clsx from "clsx";
import { useLocale } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { LOCALE_LABELS, routing, type Locale } from "@/i18n/routing";

/**
 * Switches language without losing the page.
 *
 * `usePathname` here is the locale-aware one, so it returns the route
 * without its prefix — replacing it keeps the visitor where they were
 * rather than dropping them on the home page of the language they picked,
 * which is what a plain set of links to "/tr" would do.
 *
 * A native <select> rather than a custom menu: four options, and the
 * platform's own control is the one that already works with a keyboard,
 * a screen reader and a thumb.
 */
export function LanguageSwitcher({ className }: { className?: string }) {
  const locale = useLocale() as Locale;
  const pathname = usePathname();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <div className={clsx("relative flex items-center", className)}>
      <Globe
        size={15}
        className="pointer-events-none absolute left-2 text-white/40"
        aria-hidden
      />
      <select
        value={locale}
        disabled={pending}
        onChange={(event) => {
          const next = event.target.value as Locale;
          // A transition because the new language's messages are fetched
          // from the server; without it the control appears frozen for
          // the round trip.
          startTransition(() => router.replace(pathname, { locale: next }));
        }}
        className={clsx(
          "cursor-pointer appearance-none rounded-lg border border-transparent bg-transparent py-1 pl-7 pr-2",
          "text-sm text-white/50 outline-none transition-colors",
          "hover:border-border hover:text-white focus:border-accent",
          pending && "opacity-50"
        )}
      >
        {routing.locales.map((option) => (
          // Styled for the page, but the open list is drawn by the OS and
          // inherits its own colours — hence the explicit dark background,
          // which is the one part a native select lets us set.
          <option key={option} value={option} className="bg-surface text-white">
            {LOCALE_LABELS[option]}
          </option>
        ))}
      </select>
    </div>
  );
}
