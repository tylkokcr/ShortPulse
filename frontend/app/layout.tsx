import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShortPulse — Local AI Short-Form Video Agent",
  description: "Turn a topic or script into a ready-to-post vertical video, entirely on your own machine.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
