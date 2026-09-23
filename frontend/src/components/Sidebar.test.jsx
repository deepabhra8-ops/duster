import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import Sidebar from "./Sidebar.jsx";
import Topbar from "./Topbar.jsx";

vi.mock("./AccountMenu.jsx", () => ({
  default: () => <div data-testid="account-menu" />,
}));

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

  it("keeps the account menu inside the rail", () => {
    renderSidebar({ open: true });

    expect(screen.getByTestId("account-menu")).toBeInTheDocument();
  });

  it("still renders every nav destination", () => {
    renderSidebar();

    for (const label of ["Dashboard", "Profile Mapper", "Validator"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }

    expect(screen.getByRole("button", { name: "Discovery" })).toBeInTheDocument();
  });
});

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

  it("points at the id the sidebar actually carries", () => {
    const { container } = renderSidebar();

    expect(container.querySelector(".sidebar")).toHaveAttribute("id", "app-sidebar");
  });
});
