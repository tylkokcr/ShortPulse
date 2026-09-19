import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

/**
 * Locale-aware replacements for next/link and next/navigation.
 *
 * Every internal navigation has to come through these. A bare
 * `<Link href="/library">` from a Turkish page sends the visitor to the
 * English one and silently ends their language — the prefix is not in
 * the href, and nothing about the failure looks like a failure.
 */
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
