import { defineConfig } from "@playwright/test"
export default defineConfig({
  testDir: "./tests",
  testMatch: "player-card.spec.ts",
  outputDir: "../.temp/player-card/test-results",
  reporter: "list",
  workers: 2,
  use: {
    baseURL: "http://localhost:5174",
    viewport: { width: 480, height: 1200 },
    deviceScaleFactor: 2,
  },
  webServer: {
    command: "bun run dev --port 5174 --strictPort",
    url: "http://localhost:5174",
    reuseExistingServer: !process.env.CI,
  },
})
