import { defineConfig } from "@playwright/test";

// Runs against a real backend (FastAPI + the built frontend it serves at
// /app/), not a mocked one — see frontend/e2e/README.md for how the server
// is seeded and started. Never runs against production: E2E_BASE_URL
// defaults to a local throwaway server, and DEV_AUTH_ENABLED (required for
// the ?devTelegramId= login shortcut these tests use) can never be true on
// a real deployment — see app/config.py's assert_safe_for_deployment().
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    viewport: { width: 390, height: 844 }, // matches the Mini App's mobile-only reality
  },
});
