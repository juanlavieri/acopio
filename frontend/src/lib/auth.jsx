import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken } from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const { user } = await api.get("/api/auth/me");
      setUser(user);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauth = () => setUser(null);
    window.addEventListener("acopio:unauthorized", onUnauth);
    return () => window.removeEventListener("acopio:unauthorized", onUnauth);
  }, [refresh]);

  const login = async (email, password) => {
    const { token, user } = await api.post("/api/auth/login", { email, password });
    setToken(token);
    setUser(user);
  };

  const register = async (email, name, password) => {
    const { token, user } = await api.post("/api/auth/register", { email, name, password });
    setToken(token);
    setUser(user);
  };

  const logout = async () => {
    try {
      await api.post("/api/auth/logout");
    } catch {
      /* ignore */
    }
    setToken(null);
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  return useContext(AuthCtx);
}
