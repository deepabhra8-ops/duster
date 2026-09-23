/**
 * useToast.js - access the app-wide toast notifier (ToastContext.jsx).
 * `const { showToast } = useToast(); showToast({ type: "error", title: "...", message: "..." });`
 */
import { useContext } from "react";
import { ToastContext } from "../contexts/ToastContext.jsx";

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}

export default useToast;
