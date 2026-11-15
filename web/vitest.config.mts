// Component and helper tests: `pnpm test`, or `pnpm test:coverage` for a
// coverage report in coverage/ (decision record 22). They run in a simulated
// browser (jsdom) with the network replaced by each test's own answers. The
// end-to-end tests in e2e/ are Playwright's, not these.

import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
      reporter: ["text-summary", "html", "json-summary"],
    },
  },
});
