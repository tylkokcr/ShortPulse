/** Cloudflare Turnstile's site key, or "" when the bot check is off (see
 *  components/auth/Turnstile.tsx). Its own module so server pages can read
 *  it too; a constant from a "use client" file reaches them as a client
 *  reference, not as its value. */
export const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";
