import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import {
  passwordLoginRequest,
  workosCallbackRequest,
  logoutRequest,
  saveSession,
  clearSession,
  getSession,
  isSessionValid,
  type Session,
} from '@/lib/auth';

interface AuthContextType {
  isAuthenticated: boolean;
  companyName: string;
  userName: string;
  loginWithPassword: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  loginWithWorkos: (code: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    const s = getSession();
    if (s && isSessionValid(s)) return s;
    if (s) clearSession();
    return null;
  });

  const loginWithPassword = useCallback(async (email: string, password: string) => {
    try {
      const data = await passwordLoginRequest(email.trim(), password);
      const s = saveSession(data);
      setSession(s);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : 'AUTH_ERROR' };
    }
  }, []);

  const loginWithWorkos = useCallback(async (code: string) => {
    try {
      const data = await workosCallbackRequest(code);
      const s = saveSession(data);
      setSession(s);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : 'AUTH_ERROR' };
    }
  }, []);

  const logout = useCallback(() => {
    const token = session?.token;
    if (token) logoutRequest(token);
    clearSession();
    setSession(null);
  }, [session?.token]);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: !!session,
        companyName: session?.companyName ?? '',
        userName: session?.userName ?? '',
        loginWithPassword,
        loginWithWorkos,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
