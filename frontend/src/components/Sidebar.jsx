/**
 * Sidebar.jsx - Left navigation rail.
 *
 * Navigation is driven by real routes (React Router NavLink) so the URL,
 * browser back/forward, and the active-item highlight all stay in sync.
 *
 * An icon-only rail by default. A toggle revealed on hover of the brand mark
 * (`.sb-brand-toggle`) expands it to show item labels and the brand wordmark
 * - `expanded` state below, local to this component. The mobile drawer
 * (`open`/`onClose`) is a separate, always-fully-shown mode; see its own doc
 * comment further down.
 *
 * One item, Discovery, is not a route link - it has an `accordion` (see
 * constants/appConfig.js) and opens inline, directly beneath itself, instead
 * of going anywhere on its own. That replaces the old second-tier side panel
 * (SubNav): its two catalog sections (Rule Catalog, Data Catalog) now nest
 * inside the rail rather than living beside it.
 *
 * The DQ brand badge sits at the head of the rail, above the first nav item.
 *
 * Below the `md` breakpoint the rail is an off-canvas drawer instead - see the
 * `open`/`onClose` props and App.jsx's AuthenticatedLayout. The drawer is
 * always effectively expanded (no hover to reveal a toggle on touch), so
 * `expanded` is inert there - the CSS that shows labels and the Discovery
 * accordion in the drawer is keyed off `.sidebar.is-open`, not `.expanded`.
 */
import { useEffect, useRef, useState } from "react";
import { NavLink, matchPath, useLocation } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import { NAV_SECTIONS } from "../constants/appConfig.js";
import AccountMenu from "./AccountMenu.jsx";

/**
 * An item's `icon` is an image path (starts with "/") or an emoji fallback.
 * Image icons render as a masked <span> (not <img>) - global.css uses
 * -webkit-mask/mask with the image as the mask source and `currentColor` as
 * the fill, so hover/active color changes apply to single-color source SVGs
 * without needing pre-colored variants per state.
 */
function NavIcon({ icon: Icon }) {
  if (typeof Icon === "string" && Icon.startsWith("/")) {
    return (
      <span
        className="sb-item-icon"
        style={{ "--icon-src": `url(${Icon})` }}
        aria-hidden="true"
      />
    );
  }
  if (typeof Icon === "function" || typeof Icon === "object") {
    return (
      <span className="sb-item-icon sb-item-icon-react" aria-hidden="true">
        <Icon style={{ margin: 0 }} />
      </span>
    );
  }
  return (
    <span className="sb-item-icon sb-item-icon-emoji" aria-hidden="true">
      {Icon}
    </span>
  );
}

/**
 * One catalog nested inside the Discovery accordion (Rule Catalog / Data
 * Catalog) - its own trigger and a downward list of leaf links. Starts open
 * when the current route is one of its own links, same auto-open behaviour
 * the old SubNav accordion had, and otherwise follows the user.
 */
function DiscoverySection({ section, pathname }) {
  const Icon = section.icon;
  const hasActiveItem = section.items.some((link) => matchPath(link.to, pathname));
  const [open, setOpen] = useState(hasActiveItem);

  useEffect(() => {
    if (hasActiveItem) setOpen(true);
  }, [hasActiveItem]);

  return (
    <div className={`sb-discovery-section${open ? " is-open" : ""}`}>
      <button
        type="button"
        className="sb-discovery-section-trigger"
        aria-expanded={open}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        {Icon ? <Icon size={16} strokeWidth={1.75} aria-hidden="true" /> : null}
        <span className="sb-discovery-section-label">{section.label}</span>
        <ChevronDown className="sb-discovery-chevron" size={14} strokeWidth={2} aria-hidden="true" />
      </button>
      <div className="sb-discovery-section-panel">
        <div className="sb-discovery-section-inner">
          {section.items.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) => `sb-discovery-link${isActive ? " active" : ""}`}
            >
              {link.label}
            </NavLink>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * The Discovery rail item. Unlike a plain NavLink it is a `<button>` that
 * opens its accordion in place rather than navigating anywhere itself -
 * clicking it expands the rail first if it was collapsed (there is nowhere
 * for the accordion to show otherwise), then opens.
 */
function DiscoveryItem({ item, expanded, onExpand }) {
  const { pathname } = useLocation();
  const isDescendantActive = item.accordion.some((section) =>
    section.items.some((link) => matchPath(link.to, pathname))
  );
  const [open, setOpen] = useState(isDescendantActive);

  useEffect(() => {
    if (isDescendantActive) setOpen(true);
  }, [isDescendantActive]);

  function handleClick() {
    if (!expanded) {
      onExpand();
      setOpen(true);
      return;
    }
    setOpen((wasOpen) => !wasOpen);
  }

  return (
    <div className={`sb-discovery${open ? " is-open" : ""}`}>
      <button
        type="button"
        className={`sb-item sb-discovery-trigger${isDescendantActive ? " active" : ""}`}
        title={item.label}
        aria-label={item.label}
        aria-expanded={open}
        onClick={handleClick}
      >
        <NavIcon icon={item.icon} />
        <span className="sb-item-label">{item.label}</span>
        <ChevronDown className="sb-discovery-trigger-chevron" size={14} strokeWidth={2} aria-hidden="true" />
      </button>
      <div className="sb-discovery-panel">
        <div className="sb-discovery-panel-inner">
          {item.accordion.map((section) => (
            <DiscoverySection key={section.id} section={section} pathname={pathname} />
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * `open` / `onClose` drive the mobile drawer only (see App.jsx's
 * AuthenticatedLayout). Above the `md` breakpoint the rail is always on
 * screen and both props are inert - the CSS that reads `.is-open` is scoped
 * inside the drawer media query.
 */
export default function Sidebar({ open = false, onClose }) {
  const navRef = useRef(null);
  const lastFocused = useRef(null);
  const [expanded, setExpanded] = useState(false);

  /* Focus management for the drawer (WCAG 2.4.3). Opening moves focus into the
     rail so a keyboard or screen-reader user lands on the navigation they just
     asked for; closing returns it to whatever opened it, rather than dumping
     focus at the top of the document. */
  useEffect(() => {
    if (open) {
      lastFocused.current = document.activeElement;
      navRef.current?.querySelector("a, button")?.focus();
    } else if (lastFocused.current instanceof HTMLElement) {
      lastFocused.current.focus();
      lastFocused.current = null;
    }
  }, [open]);

  /* Tab is confined to the drawer while it is open - behind it the page is
     covered by the scrim and is not meant to be reachable. */
  function onKeyDown(e) {
    if (!open || e.key !== "Tab") return;
    const focusables = navRef.current?.querySelectorAll(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusables || focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return (
    <>
      {/* Tap-to-dismiss backdrop. Rendered at every width but only made
          visible/interactive inside the drawer breakpoint, so it can animate
          rather than pop in. */}
      <div
        className={`sidebar-scrim${open ? " is-open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <nav
        id="app-sidebar"
        ref={navRef}
        onKeyDown={onKeyDown}
        className={`sidebar${open ? " is-open" : ""}${expanded ? " expanded" : ""}`}
        role="navigation"
        aria-label="Main navigation"
      >
        {/* Brand mark above the first nav item. Deliberately not a link: the
            Dashboard item just below and the topbar logo already go home, and a
            third stop would only add to the tab order and the drawer's focus
            trap. An <img>, not a NavIcon - the badge is multi-coloured, and the
            masked-span technique NavIcon uses would flatten it to one colour. */}
        <div className="sb-brand">
          <img
            className="sb-brand-logo"
            src="/icons/dq-brand.svg"
            alt="DUSTER"
            width="36"
            height="36"
          />
          <span className="sb-brand-text" aria-hidden={!expanded}>
            DUSTER
          </span>
          <button
            type="button"
            className="sb-brand-toggle"
            onClick={() => setExpanded((wasExpanded) => !wasExpanded)}
            aria-expanded={expanded}
            aria-controls="app-sidebar"
            aria-label={expanded ? "Collapse navigation" : "Expand navigation"}
          >
            <ChevronRight size={14} strokeWidth={2.5} aria-hidden="true" />
          </button>
        </div>
        <div className="sb-nav">
          {NAV_SECTIONS.map((group, i) => (
            <div key={group.section || `group-${i}`}>
              {group.section ? <div className="sb-section">{group.section}</div> : null}
              {group.items.map((item) =>
                item.accordion ? (
                  <DiscoveryItem
                    key={item.id}
                    item={item}
                    expanded={expanded}
                    onExpand={() => setExpanded(true)}
                  />
                ) : (
                  <NavLink
                    key={item.id}
                    id={`nav-${item.id}`}
                    to={`/${item.id}`}
                    className={({ isActive }) => `sb-item${isActive ? " active" : ""}`}
                    title={item.label}
                    aria-label={item.label}
                  >
                    <NavIcon icon={item.icon} />
                    <span className="sb-item-label">{item.label}</span>
                  </NavLink>
                )
              )}
            </div>
          ))}
        </div>
        <div className="sb-footer">
          <AccountMenu />
        </div>
      </nav>
    </>
  );
}
