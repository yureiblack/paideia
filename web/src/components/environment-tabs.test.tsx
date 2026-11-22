// The contents of an environment (decision record 28): the Overview, then
// the Library and Learn, numbered in that order; a document's own page is
// part of Materials.

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let pathname = "/environments/e1";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

import { EnvironmentTabs, sectionNumber, tabLabel, tabNumber } from "@/components/environment-tabs";

describe("EnvironmentTabs", () => {
  it("groups the sections as the Library and Learn, numbered in order", () => {
    pathname = "/environments/e1/summary";
    render(<EnvironmentTabs id="e1" />);
    const nav = screen.getByRole("navigation", { name: "Environment sections" });
    const library = within(nav).getByRole("group", { name: "Library" });
    const learn = within(nav).getByRole("group", { name: "Learn" });
    expect(within(library).getAllByRole("link").map((l) => l.textContent)).toEqual([
      "02Materials",
      "03Summary",
      "04Knowledge map",
      "05Search",
    ]);
    expect(within(learn).getAllByRole("link").map((l) => l.textContent)).toEqual([
      "06Roadmap",
      "07Practice",
    ]);
    expect(within(nav).getByRole("link", { name: "Summary" })).toHaveAttribute("aria-current", "page");
  });

  it("counts a document's page as Materials", () => {
    pathname = "/environments/e1/materials/d1";
    render(<EnvironmentTabs id="e1" />);
    expect(screen.getByRole("link", { name: "Materials" })).toHaveAttribute("aria-current", "location");
    expect(tabLabel("e1", pathname)).toBe("Materials");
    expect(tabNumber("e1", pathname)).toBe("02");
  });

  it("numbers a section by its name", () => {
    expect(sectionNumber("Overview")).toBe("01");
    expect(sectionNumber("Search")).toBe("05");
    expect(sectionNumber("Practice")).toBe("07");
  });
});
