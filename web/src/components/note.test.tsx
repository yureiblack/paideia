// A note in the margin (decision record 28): shown the first time a place
// is opened, put away for good with Got it, and pointing to the guide.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { Note } from "@/components/note";

beforeEach(() => window.localStorage.clear());

describe("Note", () => {
  it("explains a place until Got it puts it away", async () => {
    render(
      <Note id="knowledge-map" title="The knowledge map — where it comes from" guideStep={3}>
        Every concept here was found in your passages.
      </Note>,
    );
    const note = screen.getByRole("complementary", { name: "The knowledge map — where it comes from" });
    expect(note).toHaveTextContent("Every concept here was found in your passages.");
    expect(screen.getByRole("link", { name: "More in the guide" })).toHaveAttribute("href", "/guide#step-3");

    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("stays away once put away", () => {
    window.localStorage.setItem("paideia.note.roadmap", "away");
    render(
      <Note id="roadmap" title="The roadmap — how the order is made">
        What a concept builds on comes before it.
      </Note>,
    );
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
