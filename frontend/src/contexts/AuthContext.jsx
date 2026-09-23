/**
 * AuthContext.jsx - App-wide auth state.
 *
 * A Context (not props) because auth status is needed independently at the
 * route-guard level (App) and inside the Sidebar (sign-out button) -
 * threading it down as props would mean passing it through PageShell for no
 * reason. Mounted once at the app root, so every page shares the same
 * state without re-checking on each client-side route change.
 *
 * `status`: "checking" (initial /auth/me probe in flight) | "authenticated"
 * | "anonymous". Session keep-alive itself is server-side (sliding expiry -
 * see backend/repositories/session_repository.py): every authenticated API
 * call any page makes already pushes the session forward, so no separate
 * heartbeat is needed here.
 */
import { createContext, useCallback, useEffect, useState } from "react";
import { purgeClientState } from "../utils/purgeClientState.js";
import { login as apiLogin, logout as apiLogout, me as apiMe, setUnauthorizedHandler } from "../api/api.js";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // Always starts at "checking" and is resolved only by the /auth/me probe
  // below. There is deliberately no build-time bypass: one used to exist here,
  // hardcoding status to "authenticated" as user "dev", which disabled the
  // route guard for everyone including production builds. A switch that turns
  // off authentication is a liability even when it defaults to off, so the
  // mechanism is gone rather than merely disabled.
  const [status, setStatus] = useState("checking");
  const [username, setUsername] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiMe().then(({ ok, data }) => {
      if (cancelled) return;
      setUsername(ok ? data.username : null);
      setStatus(ok ? "authenticated" : "anonymous");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Both routes to "anonymous" must purge, not just the explicit one: a session
  // that expires server-side arrives here as a 401 and never runs logout().
  const resetToAnonymous = useCallback(() => {
    purgeClientState();
    setUsername(null);
    setStatus("anonymous");
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => resetToAnonymous());
    return () => setUnauthorizedHandler(null);
  }, [resetToAnonymous]);

  // Object shape (not positional args) so a future registration form can
  // call this the same way login() is called.
  const login = useCallback(async ({ username: u, password }) => {
    const res = await apiLogin(u, password);
    if (res.ok) {
      setUsername(res.data.username);
      setStatus("authenticated");
    }
    return res;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    resetToAnonymous();
  }, [resetToAnonymous]);

  return (
    <AuthContext.Provider value={{ status, username, login, logout }}>{children}</AuthContext.Provider>
  );
}

export default AuthProvider;
