/**
 * Formats a pack price.
 *
 * The currency comes from the server rather than a "$" in the markup: a
 * deployment can price in EUR, and a euro amount drawn with a dollar sign
 * is worse than no symbol at all.
 */
export function formatPrice(cents: number, currency = "usd"): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency.toUpperCase(),
    maximumFractionDigits: cents % 100 === 0 ? 0 : 2,
  }).format(cents / 100);
}
