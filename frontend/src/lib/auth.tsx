"use client";

// Client-side auth context. We keep the JWT in localStorage and expose the
// current user + login/register/logout. Route protection is done with a small
// <RequireAuth> wrapper rather than Next middleware: the token lives in
// localStorage (not a cookie), so the server can't read it anyway, and a
// client guard keeps the whole auth story in one place.

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, tokenStore } from "./api";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, if a token exists, resolve the user. An invalid/expired token
  // clears itself via the api layer's 401 handling.
  useEffect(() => {
    const token = tokenStore.get();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  const finishAuth = useCallback(async (token: string) => {
    tokenStore.set(token);
    setUser(await api.me());
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await api.login(email, password);
      await finishAuth(access_token);
    },
    [finishAuth],
  );

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const { access_token } = await api.register(email, password, fullName);
      await finishAuth(access_token);
    },
    [finishAuth],
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Wrap protected pages: redirects to /login once we know there's no user. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }
  return <>{children}</>;
}
