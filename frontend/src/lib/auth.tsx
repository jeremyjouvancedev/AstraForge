import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

import {
  fetchAuthSettings,
  fetchCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
  type AuthSettings,
  type AuthUser
} from "@/lib/api-client";

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  loading: boolean;
  authSettings: AuthSettings | null;
  login: (credentials: { username: string; password: string }) => Promise<AuthUser>;
  register: (payload: { username: string; password: string; email?: string }) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refreshAuthSettings: () => Promise<AuthSettings | null>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [authSettings, setAuthSettings] = useState<AuthSettings | null>(null);

  useEffect(() => {
    const loadUser = async () => {
      try {
        const [settingsResult, userResult] = await Promise.all([
          fetchAuthSettings().catch(() => null),
          fetchCurrentUser().catch(() => null)
        ]);
        const resolvedSettings = settingsResult || userResult?.auth || null;
        setAuthSettings(resolvedSettings);
        setUser(userResult || null);
      } finally {
        setLoading(false);
      }
    };
    loadUser();
  }, []);

  const login = useCallback(async (credentials: { username: string; password: string }) => {
    const result = await loginUser(credentials);
    setUser(result);
    if (result.auth) {
      setAuthSettings(result.auth);
    }
    return result;
  }, []);

  const register = useCallback(
    async (payload: { username: string; password: string; email?: string }) => {
      const result = await registerUser(payload);
      if (result.auth) {
        setAuthSettings(result.auth);
      }
      if (result.access?.status === "approved") {
        setUser(result);
      } else {
        setUser(null);
      }
      return result;
    },
    []
  );

  const logout = useCallback(async () => {
    await logoutUser();
    setUser(null);
  }, []);

  const refreshAuthSettings = useCallback(async () => {
    try {
      const settings = await fetchAuthSettings();
      setAuthSettings(settings);
      return settings;
    } catch {
      setAuthSettings(null);
      return null;
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      loading,
      authSettings,
      login,
      register,
      logout,
      refreshAuthSettings
    }),
    [user, loading, authSettings, login, register, logout, refreshAuthSettings]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
