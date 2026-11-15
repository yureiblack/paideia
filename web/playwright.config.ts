// The end-to-end tests (decision record 22): `pnpm e2e` from web/. Playwright
// starts the real API, worker and page on their own ports, database, data
// folder and Redis database, so they never touch development data and can run
// while the development servers are up. Only the language model is a stand-in
// (api/tests/e2e/). Postgres and Redis must be running: docker compose up -d.

import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const root = path.resolve(__dirname, "..");
const api = path.join(root, "api");
// Everything a run leaves behind, emptied by the next run.
const state = path.join(__dirname, "e2e", ".state");
// CI installs the backend's packages without a virtual environment.
const python = process.env.E2E_PYTHON ?? path.join(root, ".venv", "bin", "python");

const API_PORT = 8100;
const WEB_PORT = 3100;

const backend = {
  DATABASE_URL:
    process.env.E2E_DATABASE_URL ??
    "postgresql+psycopg://paideia:paideia@localhost:5432/paideia_e2e",
  DATA_DIR: path.join(state, "data"),
  REDIS_URL: "redis://localhost:6379/14",
  CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
  LOG_FORMAT: "text",
};

export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results",
  // One journey, in order, on one set of servers.
  workers: 1,
  fullyParallel: false,
  // A test that fails once is shown, with its trace, never retried away.
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 5 * 60_000,
  expect: { timeout: 60_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Started in this order, each once the one before answers.
  webServer: [
    {
      command: `"${python}" -m tests.e2e.prepare "${path.join(state, "pdfs")}" && "${python}" -m uvicorn tests.e2e.server:app --port ${API_PORT}`,
      cwd: api,
      env: backend,
      url: `http://localhost:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
    },
    {
      command: `"${python}" -m tests.e2e.worker`,
      cwd: api,
      env: backend,
      // Answers 503 until the worker has announced itself.
      url: `http://localhost:${API_PORT}/health/worker`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
    },
    {
      // The address of the API is built into the page, so the page is built
      // for this run.
      command: `pnpm build && pnpm start --port ${WEB_PORT}`,
      env: { NEXT_PUBLIC_API_BASE_URL: `http://localhost:${API_PORT}` },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
