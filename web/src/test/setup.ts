// Runs before every component test file: adds the DOM matchers
// (toBeInTheDocument, toBeDisabled and the rest) and clears the rendered page
// and the faked network after each test.

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
