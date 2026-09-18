"use client";

import { useAuth } from "./AuthProvider";
import { Landing } from "@/components/marketing/Landing";

/**
 * Gates a page behind sign-in — but only where accounts exist.
 *
 * A self-hosted install has no Supabase configured, so `enabled` is false
 * and this is a pass-through. That keeps the open-source path free of a
 * login wall it has no way to satisfy.
 *
 * Signed-out visitors on a hosted instance get the marketing landing page
 * (with sign-in embedded in it) rather than a bare login card — that's the
 * only chance to make the case for the product before asking for an email.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { loading, session, enabled } = useAuth();

  if (!enabled) return <>{children}</>;

  // The landing page, not a blank — this is also the server's render,
  // and returning null there shipped every page as an empty document.
  //
  // `data-landing-boot` is what keeps the original intent: a flash of
  // "sign in" for an already-signed-in user looks broken, so
  // SESSION_BOOT_SCRIPT marks the document before first paint and CSS
  // hides this branch where a session is already stored. A crawler has
  // neither, and gets the page.
  if (loading) {
    return (
      <div data-landing-boot>
        <Landing />
      </div>
    );
  }

  if (!session) return <Landing />;
  return <>{children}</>;
}
