/**
 * The root layout exists only to satisfy Next, which requires one.
 *
 * Everything real — <html>, the fonts, the boot scripts, the providers —
 * lives in app/[locale]/layout.tsx, because all of it depends on which
 * language the request is for. This file must not emit <html> or <body>
 * itself or there would be two of each.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
