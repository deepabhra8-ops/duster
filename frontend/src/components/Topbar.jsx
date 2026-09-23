/**
 * Topbar.jsx - Fixed navbar spanning the full viewport width, above both
 * the sidebar and the page content.
 *
 * Left: just the mobile drawer toggle. The wordmark that used to sit here
 * ("Datalytics Data Quality Engine") moved into the rail itself, shortened
 * to "Data Quality Engine", beside the brand mark in Sidebar.jsx - it shows
 * there once the rail is expanded, rather than living in the bar at every
 * width. Right: notification bell (NotificationBell - unread badge +
 * popover) and the logo link.
 *
 * The sidebar is a fixed-width icon rail on desktop, not collapsible from
 * here. The hamburger below is NOT the rail's own expand/collapse toggle: it
 * is scoped to the mobile drawer breakpoint only (`display: none` above
 * `md`), where the rail is off-canvas and would otherwise be unreachable -
 * taking sign-out, which lives inside it, with it.
 */
import { IconMenu } from "./Icons.jsx";
import NotificationBell from "./notifications/NotificationBell.jsx";

export default function Topbar({ navOpen = false, onMenuClick }) {
  return (
    <header className="topbar" role="banner">
      <div className="topbar-left">
        {/* Drawer toggle. Hidden above the `md` breakpoint, where the rail is
            permanently on screen and there is nothing to open. */}
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
