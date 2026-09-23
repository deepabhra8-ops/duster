import { IconMenu } from "./Icons.jsx";
import NotificationBell from "./notifications/NotificationBell.jsx";

export default function Topbar({ navOpen = false, onMenuClick }) {
  return (
    <header className="topbar" role="banner">
      <div className="topbar-left">
        <button
          type="button"
          className="topbar-menu-btn"
          onClick={onMenuClick}
          aria-label={navOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={navOpen}
          aria-controls="app-sidebar"
        >
          <IconMenu open={navOpen} style={{ margin: 0 }} />
        </button>
      </div>

      <div className="topbar-right">
        <NotificationBell />

        <a href="/home" className="topbar-logo-link" aria-label="DUSTER – go to Dashboard">
          <span className="topbar-logo">DUSTER</span>
        </a>
      </div>
    </header>
  );
}
