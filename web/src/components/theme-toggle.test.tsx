import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { THEME_KEY } from "@/lib/theme";

import { ThemeToggle } from "./theme-toggle";

// The system's colour scheme, which a test can change while the page is open.
let systemDark = false;
const listeners = new Set<() => void>();

beforeEach(() => {
  systemDark = false;
  listeners.clear();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return systemDark;
    },
    media: query,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// One of the three choices shown on wider screens.
const choice = (name: string) => screen.getByRole("button", { name });

describe("ThemeToggle", () => {
  it("offers auto, light and dark, with auto chosen until something else is", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Auto" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "false");
  });

  it("darkens the page when dark is chosen, and remembers it", async () => {
    render(<ThemeToggle />);
    await userEvent.click(choice("Dark"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows a choice remembered from before", () => {
    window.localStorage.setItem(THEME_KEY, "light");
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute("aria-pressed", "true");
  });

  it("follows the system on auto, also when the system changes", async () => {
    render(<ThemeToggle />);
    await userEvent.click(choice("Light"));
    await userEvent.click(choice("Auto"));
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("light");

    systemDark = true;
    act(() => listeners.forEach((listener) => listener()));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("keeps a chosen theme when the system changes", async () => {
    render(<ThemeToggle />);
    await userEvent.click(choice("Light"));
    systemDark = true;
    act(() => listeners.forEach((listener) => listener()));
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("steps through the three with one button on a phone", async () => {
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("button", { name: "Theme: Auto. Change to Light" }));
    expect(window.localStorage.getItem(THEME_KEY)).toBe("light");
    await userEvent.click(screen.getByRole("button", { name: "Theme: Light. Change to Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "Theme: Dark. Change to Auto" }));
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull();
  });
});
