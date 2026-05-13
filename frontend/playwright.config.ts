import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright smoke harness for the verify-and-review happy path.
 *
 * Assumes the backend is running at `BASE_URL` (default http://localhost:5173
 * proxied to :8000 by Vite). The default `webServer` block boots the Vite dev
 * server; the backend must already be up and seeded (`uv run uvicorn app.main:app`
 * elsewhere, or via `docker run`).
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5174";
const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8001";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  metadata: { apiUrl: API_URL },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: undefined },
    },
  ],
});
