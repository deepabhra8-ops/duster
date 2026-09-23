/**
 * Sidebar / Topbar mobile drawer.
 *
 * Below the `md` breakpoint the rail translates off-canvas (global.css), so
 * the hamburger in the Topbar is the only way to reach navigation - and, since
 * AccountMenu lives inside the rail, the only way to reach sign-out. Before
 * this existed the rail was `display: none` under 700px with nothing put in
 * its place, which left no way to change page but to type a URL.
 *
 * jsdom applies no media queries and has no viewport, so these tests cannot
 * assert the rail is visually off-canvas - that part is CSS and is verified by
 * eye. What they do pin is the wiring the CSS depends on: that the open state
 * reaches both components, that every documented way of dismissing the drawer
 * is connected, and that the button describes itself correctly to a screen
 * reader in both states. Those are the parts that silently rot.
 *
 * fireEvent rather than user-event: this repo does not depend on the latter.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import Sidebar from "./Sidebar.jsx";
import Topbar from "./Topbar.jsx";

vi.mock("./AccountMenu.jsx", () => ({
  default: () => <div data-testid="account-menu" />,
}));

/* Topbar renders the bell, which needs the notifications provider and a router. These tests are
   about the drawer toggle, not notifications (see NotificationBell.test.jsx), so it is stubbed
   the same way AccountMenu is. */
vi.mock("./notifications/NotificationBell.jsx", () => ({
  default: () => <div data-testid="notification-bell" />,
}));

function renderSidebar(props = {}) {
  return render(
    <MemoryRouter>
      <Sidebar {...props} />
    </MemoryRouter>
  );
}

describe("Sidebar drawer", () => {
  it("is closed by default - no is-open anywhere", () => {
    const { container } = renderSidebar();

    expect(container.querySelector(".sidebar")).not.toHaveClass("is-open");
    expect(container.querySelector(".sidebar-scrim")).not.toHaveClass("is-open");
  });

  it("marks both the rail and its backdrop open together", () => {
    const { container } = renderSidebar({ open: true });

    expect(container.querySelector(".sidebar")).toHaveClass("is-open");
    expect(container.querySelector(".sidebar-scrim")).toHaveClass("is-open");
  });

  it("dismisses when the backdrop is tapped", () => {
    const onClose = vi.fn();
    const { container } = renderSidebar({ open: true, onClose });

    fireEvent.click(container.querySelector(".sidebar-scrim"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  /* AccountMenu is rendered inside the rail, so a drawer that did not carry it
     would take sign-out off screen with it - the original bug. */
  it("keeps the account menu inside the rail", () => {
    renderSidebar({ open: true });

    expect(screen.getByTestId("account-menu")).toBeInTheDocument();
  });

  it("still renders every nav destination", () => {
    renderSidebar();

    for (const label of ["Dashboard", "Profile Mapper", "Validator"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }

    /* Discovery opens an inline accordion rather than going to a route of its
       own, so it is a button, not a link - see the "Discovery accordion"
       describe block below. */
    expect(screen.getByRole("button", { name: "Discovery" })).toBeInTheDocument();
  });
});

/* The rail's expand toggle and the Discovery accordion nested inside it -
   replaces the old second-tier SubNav panel (see git history), so these pin
   the behaviour that used to live there: the catalog links are reachable,
   just nested in the rail now instead of beside it. */
describe("Sidebar expand toggle", () => {
  it("starts collapsed, with labels hidden from assistive tech", () => {
    const { container } = renderSidebar();

    expect(container.querySelector(".sidebar")).not.toHaveClass("expanded");
    expect(screen.getByText("Data Quality").closest(".sb-brand-text")).toHaveAttribute(
      "aria-hidden",
      "true"
    );
  });

  it("expands the rail when the toggle is clicked", () => {
    const { container } = renderSidebar();

    fireEvent.click(screen.getByRole("button", { name: /expand navigation/i }));

    expect(container.querySelector(".sidebar")).toHaveClass("expanded");
    expect(screen.getByText("Data Quality").closest(".sb-brand-text")).toHaveAttribute(
      "aria-hidden",
      "false"
    );
  });

  it("collapses again on a second click", () => {
    const { container } = renderSidebar();
    const toggle = screen.getByRole("button", { name: /expand navigation/i });

    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /collapse navigation/i }));

    expect(container.querySelector(".sidebar")).not.toHaveClass("expanded");
  });
});

describe("Discovery accordion", () => {
  it("expands the rail and opens on click when the rail was collapsed", () => {
    const { container } = renderSidebar();

    fireEvent.click(screen.getByRole("button", { name: "Discovery" }));

    expect(container.querySelector(".sidebar")).toHaveClass("expanded");
    expect(screen.getByRole("button", { name: "Discovery" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
  });

  it("nests Rule Catalog and Data Catalog, each with their own links", () => {
    renderSidebar();

    fireEvent.click(screen.getByRole("button", { name: "Discovery" }));
    fireEvent.click(screen.getByRole("button", { name: "Rule Catalog" }));
    fireEvent.click(screen.getByRole("button", { name: "Data Catalog" }));

    for (const label of ["Dimension", "Rules", "References"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    for (const label of ["Data Assets", "Connections", "Glossary"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("toggles closed on a second click once the rail is already expanded", () => {
    renderSidebar();
    const trigger = screen.getByRole("button", { name: "Discovery" });

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});

/* WCAG 2.4.3 - focus must follow the drawer, not be stranded behind it. */
describe("Sidebar drawer focus management", () => {
  it("moves focus into the rail when it opens", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();

    const { rerender } = render(
      <MemoryRouter>
        <Sidebar open={false} onClose={() => {}} />
      </MemoryRouter>
    );

    rerender(
      <MemoryRouter>
        <Sidebar open onClose={() => {}} />
      </MemoryRouter>
    );

    expect(document.activeElement).not.toBe(opener);
    expect(document.activeElement.closest("#app-sidebar")).not.toBeNull();

    opener.remove();
  });

  it("returns focus to whatever opened it on close", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();

    const { rerender } = render(
      <MemoryRouter>
        <Sidebar open={false} onClose={() => {}} />
      </MemoryRouter>
    );
    rerender(
      <MemoryRouter>
        <Sidebar open onClose={() => {}} />
      </MemoryRouter>
    );
    rerender(
      <MemoryRouter>
        <Sidebar open={false} onClose={() => {}} />
      </MemoryRouter>
    );

    expect(document.activeElement).toBe(opener);

    opener.remove();
  });

  it("wraps Tab from the last focusable back to the first", () => {
    const { container } = renderSidebar({ open: true, onClose: () => {} });

    const focusables = container
      .querySelector("#app-sidebar")
      .querySelectorAll('a[href], button:not([disabled])');
    const last = focusables[focusables.length - 1];
    last.focus();

    fireEvent.keyDown(container.querySelector("#app-sidebar"), { key: "Tab" });

    expect(document.activeElement).toBe(focusables[0]);
  });
});

describe("Topbar drawer toggle", () => {
  it("reports the drawer state to assistive tech", () => {
    const { rerender } = render(<Topbar navOpen={false} onMenuClick={() => {}} />);

    const button = screen.getByRole("button", { name: /open navigation/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "app-sidebar");

    rerender(<Topbar navOpen onMenuClick={() => {}} />);

    const open = screen.getByRole("button", { name: /close navigation/i });
    expect(open).toHaveAttribute("aria-expanded", "true");
  });

  it("calls back when pressed", () => {
    const onMenuClick = vi.fn();
    render(<Topbar navOpen={false} onMenuClick={onMenuClick} />);

    fireEvent.click(screen.getByRole("button", { name: /open navigation/i }));

    expect(onMenuClick).toHaveBeenCalledTimes(1);
  });

  /* aria-controls above points at this id; if the rail ever loses it the
     association breaks silently. */
  it("points at the id the sidebar actually carries", () => {
    const { container } = renderSidebar();

    expect(container.querySelector(".sidebar")).toHaveAttribute("id", "app-sidebar");
  });
});
