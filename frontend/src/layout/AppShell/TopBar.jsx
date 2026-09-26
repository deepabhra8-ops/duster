import { useEffect, useRef, useState } from "react";
import { Bell, LogOut, Search } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth.js";
import { useNotifications } from "../../hooks/useNotifications.js";
import "./TopBar.css";

function initials(username) {
  const parts = String(username || "").trim().split(/[\s._-]+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
}

const NAV_ITEMS = [
  { label: "Dashboards", to: "/dashboards/dimensions" },
  { label: "Connections", to: "/connections" },
  { label: "Catalog", disabled: true },
  { label: "Quality rules", disabled: true },
  { label: "Jobs", disabled: true },
];

export function TopBar() {
  const { username, email, logout } = useAuth();
  const { unreadCount } = useNotifications();
  const [menuOpen, setMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;

    function handlePointerDown(event) {
      if (!userMenuRef.current?.contains(event.target)) {
        setMenuOpen(false);
      }
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") setMenuOpen(false);
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  return (
    <header className="app-topbar">
      <NavLink to="/dashboards/dimensions" className="app-topbar-brand">
        <img src="/icons/dq-brand.svg" width={22} height={22} alt="" aria-hidden="true" />
        <span className="app-topbar-title">Duster</span>
      </NavLink>

      <nav className="app-topbar-nav" aria-label="Primary">
        {NAV_ITEMS.map((item) =>
          item.disabled ? (
            <span key={item.label} className="tier1-link is-disabled" title="Not available yet" aria-disabled="true">
              {item.label}
            </span>
          ) : (
            <NavLink
              key={item.label}
              to={item.to}
              className={({ isActive }) => `tier1-link${isActive ? " is-active" : ""}`}
            >
              {item.label}
            </NavLink>
          )
        )}
      </nav>

      <div className="app-topbar-spacer" />

      <label htmlFor="global-search" className="sr-only">
        Search tables, columns and connections
      </label>
      <div className="search-field">
        <Search aria-hidden="true" />
        <input id="global-search" type="text" placeholder="Search tables, columns, connections…" disabled />
        <span className="kbd">⌘K</span>
      </div>

      <button type="button" className="icon-btn" aria-label="Notifications">
        <Bell size={16} aria-hidden="true" />
        {unreadCount > 0 ? <span className="app-topbar-badge" /> : null}
      </button>

      <div className="app-topbar-divider" />

      <div className="app-topbar-user" ref={userMenuRef}>
        {username ? (
          <>
            <button
              type="button"
              className="avatar"
              aria-label="Account menu"
              aria-haspopup="true"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span className="avatar-circle">{initials(username)}</span>
              <span className="app-topbar-username">{username}</span>
            </button>
            {menuOpen ? (
              <div className="account-popover" role="menu">
                <div className="account-popover-email">{email || "No email on file"}</div>
                <button
                  type="button"
                  role="menuitem"
                  className="account-popover-signout"
                  onClick={() => {
                    setMenuOpen(false);
                    logout();
                  }}
                >
                  <LogOut size={14} aria-hidden="true" />
                  Sign out
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </header>
  );
}

export default TopBar;
