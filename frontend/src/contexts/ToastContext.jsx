/**
 * ToastContext.jsx - app-wide toast notifications.
 *
 * Replaces window.alert()/ad hoc "notification" UI across the app: any page
 * that needs to tell the user something happened (a save failed, a job
 * finished, a background action succeeded) calls useToast()'s showToast()
 * instead of blocking with a native alert. Toasts stack in a fixed viewport
 * (ToastViewport.jsx, rendered once here) and auto-dismiss after `duration`
 * ms, shown via a shrinking progress bar (CSS animation, .toast-progress-fill
 * in global.css) - hovering a toast pauses both the bar and the dismiss
 * timer so a message being read doesn't vanish underneath the cursor.
 *
 * showToast({ type, title, message, duration }) - `type` is "success" |
 * "error" | "warn" | "info" (default "info"), each with its own default
 * duration (errors/warnings linger longer) unless `duration` (ms) overrides
 * it. Returns the toast's id, which can be passed to dismiss(id) to remove
 * it early (rarely needed - the close button and auto-dismiss cover almost
 * every case).
 */
import { createContext, useCallback, useState } from "react";
import ToastViewport from "../components/ToastViewport.jsx";

export const ToastContext = createContext(null);

let nextId = 1;

const DEFAULT_DURATION = {
  success: 4500,
  info: 4500,
  warn: 5500,
  error: 7000,
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    // Give the leave animation (global.css's toast-out, .18s) time to play
    // before actually dropping the toast from state.
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 200);
  }, []);

  const showToast = useCallback(({ type = "info", title = "", message = "", duration } = {}) => {
    const id = nextId++;
    const resolvedDuration = duration ?? DEFAULT_DURATION[type] ?? DEFAULT_DURATION.info;
    setToasts((prev) => [...prev, { id, type, title, message, duration: resolvedDuration, leaving: false }]);
    return id;
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, dismiss }}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export default ToastProvider;
