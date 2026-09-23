/**
 * RuleEditModal - Analyst Notes is capped at 200 characters, with a live counter.
 *
 * The backend rejects notes over PROFILE_MAP_NOTES_MAX_LEN (200); the modal used
 * to let a user type past that and only find out on Save. These tests pin the
 * UI half: the counter starts at the saved length, follows typing, and the
 * textarea carries maxLength so the browser stops input at the limit.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RuleEditModal from "./RuleEditModal.jsx";

const ROW = { "Applicable Rules": "DQ1", Column: "FirstName", "Data Type": "string" };

function renderModal(currentNotes = "") {
  render(
    <RuleEditModal
      isOpen
      onClose={vi.fn()}
      row={ROW}
      currentParams=""
      currentNotes={currentNotes}
      onSave={vi.fn()}
    />
  );
  return screen.getByPlaceholderText("Add notes (optional)");
}

describe("RuleEditModal - Analyst Notes limit", () => {
  it("shows 0/200 for an empty note and caps the textarea at 200", () => {
    const textarea = renderModal();

    expect(screen.getByText("0/200")).toBeInTheDocument();
    expect(textarea).toHaveAttribute("maxLength", "200");
  });

  it("starts the counter at the saved note's length", () => {
    renderModal("Checked with the business team");

    expect(screen.getByText("30/200")).toBeInTheDocument();
  });

  it("updates the counter as the user types", () => {
    const textarea = renderModal();

    fireEvent.change(textarea, { target: { value: "hello" } });

    expect(screen.getByText("5/200")).toBeInTheDocument();
  });
});
