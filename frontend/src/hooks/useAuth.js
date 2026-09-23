/**
 * useAuth.js - Access AuthContext (status, username, login, logout) from any
 * component. Alongside the other hooks in this folder for a consistent
 * import path (`hooks/useX.js`), even though its state lives in a Context.
 */
import { useContext } from "react";
import { AuthContext } from "../contexts/AuthContext.jsx";

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth() must be used within an <AuthProvider>");
  }
  return ctx;
}

export default useAuth;
