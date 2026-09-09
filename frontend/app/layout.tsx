import type { Metadata } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { ACCENT_BOOT_SCRIPT } from "@/components/ui/AccentSwitcher";

// Variable weight range rather than a fixed set: headlines want 600-700
// and the same face at 400 carries body text, so loading it once covers
// both without a second family.
const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "ShortPulse — Local AI Short-Form Video Agent",
  description:
    "Turn a topic or script into a ready-to-post vertical video. Script, voiceover, captions, visuals and music, assembled on your own machine — no subscription.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning covers exactly one attribute: the boot
    // script below writes data-accent onto this element before React
    // hydrates, so the server markup and the live DOM legitimately differ.
    // It suppresses the warning for this element's attributes only — not
    // for its children — which is why the script has to be the sole thing
    // that touches <html>.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${archivo.variable} ${jetbrainsMono.variable}`}
    >
      <head>
        {/* Applies the stored accent before the first paint. Inline and
            synchronous on purpose: anything deferred shows one frame of
            the default colour on every navigation. */}
        <script dangerouslySetInnerHTML={{ __html: ACCENT_BOOT_SCRIPT }} />
      </head>
      <body className="font-sans">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
