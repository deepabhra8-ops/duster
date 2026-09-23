/**
 * AccountMenu.jsx - Topbar user icon + account/profile dropdown.
 *
 * Item list is data-driven (`ACCOUNT_MENU_ITEMS`) so new entries (profile,
 * settings, theme, ...) are just array additions later, not new dropdown
 * plumbing. Sign Out is the only item today - logic moved here from the
 * old sidebar footer.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.js";

const ACCOUNT_MENU_ITEMS = [
  {
    id: "signout",
    label: "Sign Out",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
        <polyline points="16 17 21 12 16 7"></polyline>
        <line x1="21" y1="12" x2="9" y2="12"></line>
      </svg>
    ),
  }
];

export default function AccountMenu() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    function onPointerDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function handleItemClick(id) {
    setOpen(false);
    if (id === "signout") {
      await logout();
      navigate("/login", { replace: true });
    }
  }

  return (
    <div className="account-menu" ref={rootRef}>
      <button
        type="button"
        className="account-menu-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={username ? `Account menu for ${username}` : "Account menu"}
        title={username || "Account"}
      >
        <span className="avatar-circle">
          <span className="account-avatar-initials">
            {username ? username.substring(0, 1).toUpperCase() : "?"}
          </span>
        </span>
        <span className="account-avatar-username sb-item-label">{username}</span>
      </button>

      {open && (
        <div className="account-menu-dropdown" role="menu">

          {ACCOUNT_MENU_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className="account-menu-item"
              onClick={() => handleItemClick(item.id)}
            >
              <span aria-hidden="true">{item.icon}</span> {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
