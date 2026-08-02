"use client";

import { useAuth } from "./AuthProvider";
import { LoginScreen } from "./LoginScreen";

/**
 * Gates a page behind sign-in — but only where accounts exist.
 *
 * A self-hosted install has no Supabase configured, so `enabled` is false
 * and this is a pass-through. That keeps the open-source path free of a
 * login wall it has no way to satisfy.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { loading, session, enabled } = useAuth();

  if (!enabled) return <>{children}</>;

  // Deliberately blank rather than a spinner: the session lookup resolves
  // from local storage in a few milliseconds, and a flash of "sign in" for
  // an already-signed-in user looks broken.
  if (loading) return null;

  if (!session) return <LoginScreen />;
  return <>{children}</>;
}
