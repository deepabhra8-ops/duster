import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import TopBar from "./layout/AppShell/TopBar.jsx";
import Login from "./pages/Login.jsx";
import NotFound from "./pages/NotFound.jsx";
import ControlRoomPage from "./pages/ControlRoom/ControlRoomPage.jsx";
import { AuthProvider } from "./contexts/AuthContext.jsx";
import { NotificationsProvider } from "./contexts/NotificationsContext.jsx";
import { ToastProvider } from "./contexts/ToastContext.jsx";
import { useAuth } from "./hooks/useAuth.js";
import { useDisableContextMenu } from "./hooks/useDisableContextMenu.js";
import { DEFAULT_ROUTE } from "./constants/appConfig.js";

function AuthenticatedLayout({ children }) {
  const { status } = useAuth();

  if (status === "checking") {
    return <div className="auth-loading">Loading&hellip;</div>;
  }

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  return (
    <NotificationsProvider>
      <TopBar />
      {children}
    </NotificationsProvider>
  );
}

export default function App() {
  useDisableContextMenu();

  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Navigate to={DEFAULT_ROUTE} replace />} />
            <Route
              path="/control-room"
              element={
                <AuthenticatedLayout>
                  <ControlRoomPage />
                </AuthenticatedLayout>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}
