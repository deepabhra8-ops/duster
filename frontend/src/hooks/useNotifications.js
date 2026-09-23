import { useContext } from "react";
import { NotificationsContext } from "../contexts/NotificationsContext.jsx";

export function useNotifications() {
  const ctx = useContext(NotificationsContext);
  if (!ctx) {
    throw new Error("useNotifications() must be used within a <NotificationsProvider>");
  }
  return ctx;
}

export default useNotifications;
