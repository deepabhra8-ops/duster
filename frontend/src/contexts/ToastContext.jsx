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
