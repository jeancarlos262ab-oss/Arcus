import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { fetchMe, getLoginUrl, logout as logoutRequest, type AuthMe } from "@/lib/authApi";
import { ApiConfigError } from "@/lib/api";

interface AuthContextValue {
  loading: boolean;
  /** null mientras carga o si no hay sesión; nunca datos simulados. */
  user: AuthMe | null;
  /** Error de configuración (p. ej. VITE_API_BASE_URL faltante), distinto de "no logueado". */
  configError: string | null;
  /** Redirige el navegador entero a la pantalla real de consentimiento de GitHub. */
  login: () => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Identidad real del usuario, verificada contra la cookie de sesión emitida
 * por `auth_api.py` tras un login de GitHub genuino. Nunca asume un usuario
 * por defecto: sin sesión válida, `user` es `null` y el dashboard debe pedir
 * login antes de mostrar cualquier dato.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<AuthMe | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const checkSession = useCallback(async () => {
    setLoading(true);
    try {
      const me = await fetchMe();
      setUser(me);
      setConfigError(null);
    } catch (err) {
      setUser(null);
      setConfigError(err instanceof ApiConfigError ? err.message : null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  const login = useCallback(() => {
    window.location.assign(getLoginUrl());
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ loading, user, configError, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
