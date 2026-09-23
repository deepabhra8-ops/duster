/**
 * App.jsx - Root component and route table.
 *
 * Uses React Router (BrowserRouter) for navigation - the current page lives
 * in the URL, not in a localStorage-backed "activePage" string. This gives
 * real browser back/forward support, deep-linkable pages/jobs, and shareable
 * URLs.
 *
 * AuthProvider wraps everything so auth state is available both to the
 * route guard below and to the Sidebar's sign-out button. "/login" is the
 * only route reachable without a session; every other route is nested under
 * the pathless AuthenticatedLayout route, which redirects to "/login"
 * whenever there is no valid session - including right after sign-out, since
 * it re-evaluates on every render, so there is no page a signed-out user can
 * land back on without logging in again. The originally requested path is
 * deliberately not remembered: login always lands on DEFAULT_ROUTE (the
 * dashboard).
 *
 * Also performs a one-time backend health check and surfaces a dismissable
 * banner if the backend API is unreachable.
 */
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

/** Layout route element: gates Topbar + Sidebar + PageShell (i.e. every page below) behind a valid session. */
function AuthenticatedLayout() {
  const { status } = useAuth();
  const location = useLocation();

  /* Mobile navigation drawer. Below the `md` breakpoint the sidebar rail
     translates off-canvas (see global.css), so this is the only way to reach
     navigation - and, since AccountMenu lives inside the rail, the only way to
     reach sign-out. It is held here rather than inside Sidebar because Topbar's
     hamburger drives it and the two are siblings. */
  const [navOpen, setNavOpen] = useState(false);

  /* Close on navigation: tapping an item would otherwise leave the drawer
     covering the page it just opened. */
  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  /* Escape closes it, matching every other dismissable surface in the app. */
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

  /* Only ever rendered for an authenticated user (both other cases returned above), so the
     provider - which fetches and opens a live stream on mount - never runs on the login screen,
     and is torn down, its state discarded, the moment the session ends. */
  return (
    <NotificationsProvider>
      {/* WCAG 2.4.1 - first thing in the tab order on every page. */}
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
  /* App-wide, so it covers the login screen too - and mounted here rather than
     per page so no future route can forget it. See the hook for what it is and
     is not: a deterrent against casual right-click, not a control. */
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
              {/* The /run/* flow and the /jobs page were removed: nothing in the
                  sidebar linked to any of them, so they were reachable only by
                  typing a URL - and Run Validation still pointed at
                  /run/validator, which is why it rendered a stale pre-V2 UI over
                  the current one. The supported paths are /profile-mapper and
                  /validator. Anything still holding an old /run or /jobs link
                  now lands on NotFound rather than a second, divergent UI. */}
              {/* Rule Catalog destinations, reached via the Discovery accordion
                  in Sidebar.jsx. Empty for now - swap in the real page when it
                  is designed. */}
              <Route path="/rules/catalog/dimension" element={<PagePlaceholder label="Dimension" />} />
              <Route path="/rules/catalog/rules" element={<PagePlaceholder label="Rules" />} />
              {/* References (Rule Catalog's third link) opens the real Rule
                  Reference page - the dimension filter it supports lives in
                  this same optional URL segment. */}
              <Route path="/rules/:dimension?" element={<Rules />} />
              {/* Data Catalog destinations, also reached via the Discovery
                  accordion. Connections points at the existing Connections
                  page (/configure); Assets and Glossary are still empty -
                  swap in real pages when they are designed. */}
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
