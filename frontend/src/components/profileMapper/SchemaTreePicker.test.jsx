import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const TABLES = {
  public: ["claim", "policy", "member", "provider", "payment", "audit_log"],
  staging: ["stg_donation_behavior_modeling"],
};

vi.mock("../../hooks/useCatalog.js", () => ({
  useCatalog: () => ({
    loadTables: vi.fn(),
    loadColumns: vi.fn(),
    tablesFor: (schema) => ({
      items: TABLES[schema] || [],
      loading: false,
      loaded: true,
      error: "",
    }),
    columnsFor: () => ({
      items: ["id", "created_at"],
      loading: false,
      loaded: true,
      error: "",
    }),
  }),
}));

import SchemaTreePicker, { MAX_TABLES } from "./SchemaTreePicker.jsx";

const SCHEMAS = ["public", "staging"];

function renderPicker(initial = [{ schema: "", table: "", column: "", locked: false }]) {
  const state = { rows: initial };
  const onChange = vi.fn((rows) => {
    state.rows = rows;
    rerender();
  });
  let rerender;
  const utils = render(
    <SchemaTreePicker rows={state.rows} onChange={onChange} connectionId="c1" schemas={SCHEMAS} />
  );
  rerender = () =>
    utils.rerender(
      <SchemaTreePicker rows={state.rows} onChange={onChange} connectionId="c1" schemas={SCHEMAS} />
    );
  return { state, onChange };
}

const expand = (schema) => fireEvent.click(screen.getByRole("button", { name: new RegExp(schema) }));
const tick = (table) => fireEvent.click(screen.getByRole("checkbox", { name: table }));

describe("SchemaTreePicker", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not show a schema's tables until it is expanded", () => {
    renderPicker();
    expect(screen.queryByRole("checkbox", { name: "claim" })).not.toBeInTheDocument();

    expand("public");
    expect(screen.getByRole("checkbox", { name: "claim" })).toBeInTheDocument();
  });

  it("emits a locked row for a ticked table, so the modal accepts it", () => {
    const { state } = renderPicker();
    expand("public");
    tick("claim");

    expect(state.rows).toEqual([
      { schema: "public", table: "claim", column: "", locked: true },
    ]);
  });

  it("drops the placeholder row instead of carrying a blank selection", () => {
    const { state } = renderPicker();
    expand("public");
    tick("claim");

    expect(state.rows).toHaveLength(1);
    expect(state.rows.every((r) => r.schema && r.table)).toBe(true);
  });

  it("unticking a table removes only that row", () => {
    const { state } = renderPicker();
    expand("public");
    tick("claim");
    tick("policy");
    tick("claim");

    expect(state.rows.map((r) => r.table)).toEqual(["policy"]);
  });

  it(`allows ${MAX_TABLES} tables and blocks the next one`, () => {
    const { state } = renderPicker();
    expand("public");

    TABLES.public.slice(0, MAX_TABLES).forEach(tick);
    expect(state.rows).toHaveLength(MAX_TABLES);

    const sixth = screen.getByRole("checkbox", { name: TABLES.public[MAX_TABLES] });
    expect(sixth).toBeDisabled();

    fireEvent.click(sixth);
    expect(state.rows).toHaveLength(MAX_TABLES);
  });

  it("frees a slot again when a selected table is unticked at the limit", () => {
    const { state } = renderPicker();
    expand("public");
    TABLES.public.slice(0, MAX_TABLES).forEach(tick);

    tick(TABLES.public[0]);
    expect(state.rows).toHaveLength(MAX_TABLES - 1);

    tick(TABLES.public[MAX_TABLES]);
    expect(state.rows).toHaveLength(MAX_TABLES);
    expect(state.rows.map((r) => r.table)).toContain(TABLES.public[MAX_TABLES]);
  });

  it("keeps selections from one schema when another is expanded", () => {
    const { state } = renderPicker();
    expand("public");
    tick("claim");
    expand("staging");
    tick("stg_donation_behavior_modeling");

    expect(state.rows.map((r) => `${r.schema}.${r.table}`)).toEqual([
      "public.claim",
      "staging.stg_donation_behavior_modeling",
    ]);
  });

  it("filters the tree by table name", () => {
    renderPicker();
    expand("public");

    fireEvent.change(screen.getByLabelText(/filter schemas and tables/i), {
      target: { value: "polic" },
    });

    expect(screen.getByRole("checkbox", { name: "policy" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "claim" })).not.toBeInTheDocument();
  });

  it("shows loading placeholders, not an empty state, before the fetch lands", async () => {
    vi.resetModules();
    vi.doMock("../../hooks/useCatalog.js", () => ({
      useCatalog: () => ({
        loadTables: vi.fn(),
        loadColumns: vi.fn(),
        tablesFor: () => ({ items: [], loading: false, loaded: false, error: "" }),
        columnsFor: () => ({ items: [], loading: false, loaded: false, error: "" }),
      }),
    }));
    const { default: Picker } = await import("./SchemaTreePicker.jsx");

    render(
      <Picker rows={[]} onChange={vi.fn()} connectionId="c1" schemas={SCHEMAS} />
    );
    fireEvent.click(screen.getByRole("button", { name: /public/ }));

    expect(screen.getByLabelText(/loading tables/i)).toBeInTheDocument();
    expect(screen.queryByText(/no tables in this schema/i)).not.toBeInTheDocument();

    vi.doUnmock("../../hooks/useCatalog.js");
    vi.resetModules();
  });

  it("says so when the connection has no schemas", () => {
    render(<SchemaTreePicker rows={[]} onChange={vi.fn()} connectionId="c1" schemas={[]} />);
    expect(screen.getByText(/no schemas available/i)).toBeInTheDocument();
  });
});
