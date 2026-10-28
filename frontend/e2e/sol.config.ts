import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";
const artifacts = fileURLToPath(new URL("../../outputs/visual-review/sol-final/", import.meta.url));
export default defineConfig({
  testDir: "./sol",
  testMatch: "*.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 60000,
  reporter: [["list"], ["json", { outputFile: `${artifacts}/results.json` }]],
  outputDir: `${artifacts}/test-results`,
  use: {
    actionTimeout: 10000,
    navigationTimeout: 15000,
    baseURL: "http://127.0.0.1:5176",
    viewport: { width: 1440, height: 900 },
    locale: "it-IT",
    timezoneId: "Europe/Rome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --config e2e/sol/vite-isolated.config.ts",
    cwd: fileURLToPath(new URL("../", import.meta.url)),
    url: "http://127.0.0.1:5176",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
