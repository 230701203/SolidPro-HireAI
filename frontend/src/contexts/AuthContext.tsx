import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, rememberMe: boolean) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<User | null>;
  setUser: (u: User | null) => void;
  hasPermission: (code: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get<User>("/auth/me");
      setUser(data);
      return data;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    const expired = () => {
      queryClient.clear();
      setUser(null);
    };
    const mustChange = () => void refresh();
    window.addEventListener("auth:expired", expired);
    window.addEventListener("auth:password-change-required", mustChange);
    return () => {
      window.removeEventListener("auth:expired", expired);
      window.removeEventListener("auth:password-change-required", mustChange);
    };
  }, [queryClient, refresh]);

  const login = useCallback(async (email: string, password: string, rememberMe: boolean) => {
    const { data } = await api.post<User>("/auth/login", { email, password, remember_me: rememberMe });
    setUser(data);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      queryClient.clear();
      setUser(null);
    }
  }, [queryClient]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login,
      logout,
      refresh,
      setUser,
      hasPermission: (code) => !!user && (user.role === "admin" || user.permissions.includes(code)),
    }),
    [user, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
