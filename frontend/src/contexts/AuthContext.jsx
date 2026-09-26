import { createContext, useCallback, useEffect, useState } from "react";
import { purgeClientState } from "../utils/purgeClientState.js";
import { login as apiLogin, logout as apiLogout, me as apiMe, setUnauthorizedHandler } from "../api/api.js";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState("checking");
  const [username, setUsername] = useState(null);
  const [email, setEmail] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiMe().then(({ ok, data }) => {
      if (cancelled) return;
      setUsername(ok ? data.username : null);
      setEmail(ok ? data.email : null);
      setStatus(ok ? "authenticated" : "anonymous");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const resetToAnonymous = useCallback(() => {
    purgeClientState();
    setUsername(null);
    setEmail(null);
    setStatus("anonymous");
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => resetToAnonymous());
    return () => setUnauthorizedHandler(null);
  }, [resetToAnonymous]);

  const login = useCallback(async ({ username: u, password }) => {
    const res = await apiLogin(u, password);
    if (res.ok) {
      setUsername(res.data.username);
      setEmail(res.data.email);
      setStatus("authenticated");
    }
    return res;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    resetToAnonymous();
  }, [resetToAnonymous]);

  return (
    <AuthContext.Provider value={{ status, username, email, login, logout }}>{children}</AuthContext.Provider>
  );
}

export default AuthProvider;
