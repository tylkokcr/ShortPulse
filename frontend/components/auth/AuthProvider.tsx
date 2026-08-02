"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, authEnabled } from "@/lib/supabase";

interface AuthState {
  /** True while the initial session lookup is in flight. Rendering a login
   *  screen before this settles would flash sign-in at someone who is
   *  already signed in. */
  loading: boolean;
  session: Session | null;
  /** False on a self-hosted install: there are no accounts, and no part of
   *  the UI should suggest otherwise. */
  enabled: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  loading: false,
  session: null,
  enabled: false,
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(authEnabled);

  useEffect(() => {
    if (!supabase) return;

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    // Covers sign-in, sign-out and the automatic token refresh — without
    // this the app would keep using an access token until it expired and
    // then start getting 401s.
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });

    return () => subscription.subscription.unsubscribe();
  }, []);

  async function signOut() {
    await supabase?.auth.signOut();
  }

  return (
    <AuthContext.Provider value={{ loading, session, enabled: authEnabled, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
