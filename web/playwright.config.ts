import { defineConfig, devices } from "@playwright/test";

/**
 * The smoke test of the built site (`npm run test:e2e`): built over the small store of
 * `e2e/data`, served by `vite preview`, opened in Chromium.
 */
export default defineConfig({
  testDir: "e2e",
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: "http://localhost:4173/", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command:
      "vite build --outDir e2e/dist --emptyOutDir && vite preview --outDir e2e/dist --port 4173 --strictPort",
    // A budget of 3 papers: the store's older day loads from the search shards (PERF-1).
    env: { PREPRINT_RADAR_DATA_DIR: "e2e/data", VITE_PAPER_BUDGET: "3" },
    url: "http://localhost:4173/",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
