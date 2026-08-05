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
  // The three specs share one SQLite-backed server (see e2e/README.md) —
  // SQLite locks the whole file on a write, so concurrent workers racing
  // to approve/register/create against it intermittently fail with
  // "database is locked", not a real bug in the app under test. Postgres
  // wouldn't have this limitation; SQLite was chosen here specifically to
  // avoid needing a DB service container just for E2E fixtures.
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    viewport: { width: 390, height: 844 }, // matches the Mini App's mobile-only reality
  },
});
