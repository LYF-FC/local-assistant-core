import { defineConfig } from "@playwright/test";

if (process.env.BUTLER_BROWSER_TESTS !== "1" || process.env.BUTLER_ENV !== "test") throw new Error("Browser acceptance requires the disposable test environment");
export default defineConfig({
  testDir: "./e2e", workers: 1, retries: 0, reporter: "line", timeout: 30000,
  use: { baseURL: process.env.BUTLER_E2E_ORIGIN, ignoreHTTPSErrors: false, trace: "off", screenshot: "off", video: "off", browserName: "chromium" },
});
