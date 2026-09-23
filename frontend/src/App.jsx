import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Topbar from "./components/Topbar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import PageShell from "./components/PageShell.jsx";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Connections from "./pages/Connections.jsx";
import { IconWarning } from "./components/Icons.jsx";
import { useDisableContextMenu } from "./hooks/useDisableContextMenu.js";
import ProfileMapper from "./pages/ProfileMapper.jsx";
import ProfileMapperJob from "./pages/ProfileMapperJob.jsx";
import Validator from "./pages/Validator.jsx";
import ValidatorJob from "./pages/ValidatorJob.jsx";
import Rules from "./pages/Rules.jsx";
import PagePlaceholder from "./pages/PagePlaceholder.jsx";
import NotFound from "./pages/NotFound.jsx";
import { AuthProvider } from "./contexts/AuthContext.jsx";
import { NotificationsProvider } from "./contexts/NotificationsContext.jsx";
import { ToastProvider } from "./contexts/ToastContext.jsx";
import { useAuth } from "./hooks/useAuth.js";
import { healthCheck } from "./api/api.js";
import { DEFAULT_ROUTE } from "./constants/appConfig.js";

function ApiBanner() {
  const [down, setDown] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    healthCheck().then(({ ok }) => {
      if (!cancelled) setDown(!ok);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!down || dismissed) return null;

  return (
    <div className="alert alert-err">
      <IconWarning style={{ color: "var(--red)", verticalAlign: "text-bottom" }} /> <strong>Backend API not running.</strong> Start with: <code>python backend/app.py</code>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        style={{ marginLeft: "12px" }}
        onClick={() => setDismissed(true)}
      >
        Dismiss
      </button>
    </div>
  );
}

function AuthenticatedLayout() {
  const { status } = useAuth();
  const location = useLocation();

  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!navOpen) return undefined;
    function onKeyDown(e) {
      if (e.key === "Escape") setNavOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navOpen]);

  if (status === "checking") {
    return <div className="auth-loading">Loading…</div>;
  }

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  return (
    <NotificationsProvider>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <Topbar navOpen={navOpen} onMenuClick={() => setNavOpen((open) => !open)} />
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <PageShell banner={<ApiBanner />} />
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

            <Route element={<AuthenticatedLayout />}>
              <Route path="/" element={<Navigate to={DEFAULT_ROUTE} replace />} />
              <Route path="/home" element={<Home />} />
              <Route path="/configure" element={<Connections />} />
              <Route path="/profile-mapper" element={<ProfileMapper />} />
              <Route path="/profile-mapper/:jobId" element={<ProfileMapperJob />} />
              <Route path="/validator" element={<Validator />} />
              <Route path="/validator/:jobId" element={<ValidatorJob />} />
              <Route path="/rules/catalog/dimension" element={<PagePlaceholder label="Dimension" />} />
              <Route path="/rules/catalog/rules" element={<PagePlaceholder label="Rules" />} />
              <Route path="/rules/:dimension?" element={<Rules />} />
              <Route path="/data-catalog" element={<PagePlaceholder label="Data Catalog" />} />
              <Route path="/data-catalog/assets" element={<PagePlaceholder label="Data Assets" />} />
              <Route path="/data-catalog/glossary" element={<PagePlaceholder label="Glossary" />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}
