/**
 * Formats a pack price.
 *
 * The currency comes from the server rather than a "$" in the markup: a
 * deployment can price in EUR, and a euro amount drawn with a dollar sign
 * is worse than no symbol at all.
 */
/**
 * `locale` is the page's, never the browser's default: with `undefined` the
 * server formatted "$11.90" and a Turkish browser "$11,90", and React threw
 * the whole pricing section away on hydration.
 */
export function formatPrice(cents: number, currency = "usd", locale = "en"): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currency.toUpperCase(),
    maximumFractionDigits: cents % 100 === 0 ? 0 : 2,
  }).format(cents / 100);
}
