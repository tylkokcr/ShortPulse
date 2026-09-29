import { Facebook, Instagram, Music2, Youtube } from "lucide-react";
import type { SocialPlatform } from "@/lib/types";

/**
 * How each platform is named and drawn, in one place.
 *
 * There were two copies of this — the connections page and the publish
 * panel — and adding a fourth platform broke both, which is the whole
 * argument. A label that differs between the screen where you connect an
 * account and the screen where you post to it is the kind of thing
 * nobody files a bug about and everybody notices.
 */
export const PLATFORM_LABELS: Record<SocialPlatform, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
};

export const PLATFORM_ICONS: Record<SocialPlatform, typeof Youtube> = {
  youtube: Youtube,
  instagram: Instagram,
  facebook: Facebook,
  // lucide has no TikTok mark; a music note is the closest honest stand-in
  // and is not pretending to be their logo.
  tiktok: Music2,
};

/**
 * Platforms shown as on the way, with no way to connect them yet.
 *
 * Instagram and Facebook publishing is built, but Meta's app review needs
 * a registered business (a JDG) and that registration is still pending.
 * Until it goes through, a Connect button would lead to Meta's own
 * "app not available" screen — so they are listed, marked as in progress,
 * and cannot be pressed. Empty this list to switch them back on; nothing
 * else about them changes.
 */
export const COMING_SOON: readonly SocialPlatform[] = ["instagram", "facebook"];

export function isComingSoon(platform: SocialPlatform): boolean {
  return COMING_SOON.includes(platform);
}
