import { defineConfig, devices } from "@playwright/test";

// These tests hit the real FastAPI backend (register/login/etc.), not a mock - `webServer`
// below only starts the Next.js dev server. Run `python run_api.py` from `backend/`
// separately first (see CLAUDE.md). Fully automating both together is Phase 11's job
// (plan.md: "npm run test:e2e (spins up the dev server + backend)"), not this phase's.
export default defineConfig({
  testDir: "./e2e",
  // Serial, not parallel: every test mutates the same real Supabase DB through one shared
  // dev backend, so concurrent workers just contend for the same single-process backend
  // (measured: N concurrent /auth/logout calls with Redis unreachable serialize behind
  // Redis's connection-pool lock, multiplying an already fail-open-but-slow path).
  workers: 1,
  retries: 0,
  reporter: "list",
  timeout: 30_000,
  expect: {
    // Every auth call still tries Redis first (rate limiter, revocation cache) before
    // failing open - fine in real usage (Redis is normally up), but adds a few real
    // seconds per request in this environment where it's deliberately unreachable.
    timeout: 15_000,
  },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
