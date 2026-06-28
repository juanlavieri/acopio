import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "./api";
import { useAuth } from "./auth.jsx";

const ScopeCtx = createContext(null);
const ACTIVE_KEY = "acopio_active_center";

export function ScopeProvider({ children }) {
  const { user } = useAuth();
  const [centers, setCenters] = useState([]);
  const [activeCenter, setActiveCenterState] = useState(localStorage.getItem(ACTIVE_KEY) || "");
  const [loading, setLoading] = useState(true);

  const fixedCenter = user?.center_id || null; // volunteers / center managers
  const needsCenterPicker = !!user && !fixedCenter; // country / regional managers

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const { centers } = await api.get("/api/org/centers");
      setCenters(centers);
    } catch {
      setCenters([]);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    load();
    const onChange = () => load();
    window.addEventListener("acopio:org-changed", onChange);
    return () => window.removeEventListener("acopio:org-changed", onChange);
  }, [load]);

  const setActiveCenter = useCallback((id) => {
    setActiveCenterState(id);
    localStorage.setItem(ACTIVE_KEY, id || "");
  }, []);

  // The center id used to filter views: fixed for center-scoped users.
  const viewCenter = fixedCenter || activeCenter || "";
  // The center id used as a default target for actions.
  const actionCenter = fixedCenter || activeCenter || (centers.length === 1 ? centers[0].id : "");

  return (
    <ScopeCtx.Provider
      value={{
        centers,
        loading,
        fixedCenter,
        needsCenterPicker,
        activeCenter,
        setActiveCenter,
        viewCenter,
        actionCenter,
        reload: load,
      }}
    >
      {children}
    </ScopeCtx.Provider>
  );
}

export function useScope() {
  return useContext(ScopeCtx);
}
