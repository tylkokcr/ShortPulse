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
