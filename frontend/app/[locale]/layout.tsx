import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Archivo, JetBrains_Mono } from "next/font/google";
import "../globals.css";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { ACCENT_BOOT_SCRIPT } from "@/components/ui/accentBoot";
import { SESSION_BOOT_SCRIPT } from "@/components/auth/sessionBoot";
import { RAIL_BOOT_SCRIPT } from "@/components/layout/railBoot";
import { routing } from "@/i18n/routing";
import { siteUrl } from "@/lib/siteUrl";

// latin-ext as well as latin, which is not optional once the UI speaks
// Turkish and Polish: `ğ ş ı İ` and `ą ć ę ł ń ś ź ż` all live there, and
// a face that lacks them does not fail — the browser silently swaps in a
// system font for those glyphs alone, so the typeface changes in the
// middle of a word. German is fine either way (ä ö ü ß are in latin).
// Same failure mode as the caption fonts, one layer up.
const archivo = Archivo({
  subsets: ["latin", "latin-ext"],
  variable: "--font-archivo",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500"],
});

const site = siteUrl();

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta" });

  // One canonical per language, plus the hreflang set — the blanket
  // `canonical: "/"` this replaced pointed every page at the English root,
  // which would have told Google the three translations were duplicates of
  // it and asked it to drop them.
  const path = locale === routing.defaultLocale ? "" : `/${locale}`;
  const languages = Object.fromEntries(
    routing.locales.map((l) => [l, l === routing.defaultLocale ? "/" : `/${l}`])
  );

  return {
    ...(site
      ? {
          metadataBase: new URL(site),
          alternates: {
            canonical: path || "/",
            languages: { ...languages, "x-default": "/" },
          },
        }
      : {}),
    title: t("title"),
    description: t("description"),
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();

  // Opts the locale's pages back into static rendering, which they lose
  // by default once anything reads the request.
  setRequestLocale(locale);

  // Both scripts must come from modules without "use client" on them.
  // A client module does not export values to the server, it exports
  // references, and interpolating one into a template literal yields the
  // source of a stub that throws — which is what shipped for a while: a
  // head script that was a syntax error, so neither the accent nor the
  // session marker ever applied, with nothing in the build or the console
  // to say so. Cheap to check, and it fails the build rather than the page.
  for (const [name, script] of [
    ["ACCENT_BOOT_SCRIPT", ACCENT_BOOT_SCRIPT],
    ["SESSION_BOOT_SCRIPT", SESSION_BOOT_SCRIPT],
    ["RAIL_BOOT_SCRIPT", RAIL_BOOT_SCRIPT],
  ] as const) {
    if (typeof script !== "string") {
      throw new Error(`${name} did not reach the server as a string — is its module a client module?`);
    }
  }

  return (
    // suppressHydrationWarning covers exactly one attribute: the boot
    // script below writes data-accent onto this element before React
    // hydrates, so the server markup and the live DOM legitimately differ.
    // It suppresses the warning for this element's attributes only — not
    // for its children — which is why the script has to be the sole thing
    // that touches <html>. `lang` is set here on the server rather than by
    // a second script, which keeps that rule intact.
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${archivo.variable} ${jetbrainsMono.variable}`}
    >
      <head>
        {/* Applies the stored accent before the first paint. Inline and
            synchronous on purpose: anything deferred shows one frame of
            the default colour on every navigation. */}
        <script dangerouslySetInnerHTML={{ __html: `${ACCENT_BOOT_SCRIPT}\n${SESSION_BOOT_SCRIPT}\n${RAIL_BOOT_SCRIPT}` }} />
      </head>
      <body className="font-sans">
        <NextIntlClientProvider>
          <AuthProvider>{children}</AuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
