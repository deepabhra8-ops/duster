import { useEffect, useRef, useState } from "react";
import { NavLink, matchPath, useLocation } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import { NAV_SECTIONS } from "../constants/appConfig.js";
import AccountMenu from "./AccountMenu.jsx";

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

export default function Sidebar({ open = false, onClose }) {
  const navRef = useRef(null);
  const lastFocused = useRef(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (open) {
      lastFocused.current = document.activeElement;
      navRef.current?.querySelector("a, button")?.focus();
    } else if (lastFocused.current instanceof HTMLElement) {
      lastFocused.current.focus();
      lastFocused.current = null;
    }
  }, [open]);

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
