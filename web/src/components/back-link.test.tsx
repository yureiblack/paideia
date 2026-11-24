// The guide's link back (back-link.tsx): to the page it was opened from,
// as the browser's back button goes, passing over the guide's own steps;
// home when the tab started on the guide or the browser cannot say.

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BackLink } from "@/components/back-link";

// A tab's history in the Navigation API, the last address the current one.
function history(...paths: string[]) {
  const entries = paths.map((path, index) => ({
    key: `key-${index}`,
    index,
    url: `http://localhost:3000${path}`,
  }));
  const navigation = Object.assign(new EventTarget(), {
    currentEntry: entries[entries.length - 1],
    entries: () => entries,
    traverseTo: vi.fn(),
  });
  vi.stubGlobal("navigation", navigation);
  return navigation;
}

function renderLink() {
  render(<BackLink fallback="/" fallbackLabel="Your environments" />);
}

describe("BackLink", () => {
  it("goes back to the page the guide was opened from", async () => {
    const navigation = history("/", "/environments/e1", "/environments/e1/practice", "/guide#step-4");
    renderLink();
    const link = screen.getByRole("link", { name: "Back" });
    expect(link).toHaveAttribute("href", "/environments/e1/practice");

    await userEvent.click(link);
    expect(navigation.traverseTo).toHaveBeenCalledWith("key-2");
  });

  it("passes over moves between the guide's steps", async () => {
    const navigation = history("/environments/e1/roadmap?stage=2", "/guide", "/guide#step-2", "/guide#step-5");
    renderLink();
    expect(screen.getByRole("link", { name: "Back" })).toHaveAttribute(
      "href",
      "/environments/e1/roadmap?stage=2",
    );

    await userEvent.click(screen.getByRole("link", { name: "Back" }));
    expect(navigation.traverseTo).toHaveBeenCalledWith("key-0");
  });

  it("leaves a click for a new tab to the browser", () => {
    const navigation = history("/environments/e1/materials", "/guide");
    renderLink();
    const link = screen.getByRole("link", { name: "Back" });
    // Nothing else is under test here, so the browser's own handling is
    // stopped once the link has had its turn.
    link.parentElement!.addEventListener("click", (event) => event.preventDefault());

    fireEvent.click(link, { metaKey: true });
    fireEvent.click(link, { ctrlKey: true });
    expect(navigation.traverseTo).not.toHaveBeenCalled();
  });

  it("goes home when the tab started on the guide", () => {
    history("/guide", "/guide#step-3");
    renderLink();
    expect(screen.getByRole("link", { name: "Your environments" })).toHaveAttribute("href", "/");
  });

  it("goes home when the browser has no Navigation API", () => {
    renderLink();
    expect(screen.getByRole("link", { name: "Your environments" })).toHaveAttribute("href", "/");
  });
});
