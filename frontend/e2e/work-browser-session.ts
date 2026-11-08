import { expect } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";

type Cookies = Awaited<ReturnType<BrowserContext["cookies"]>>;
const sessions = new Map<string, Cookies>();

/** Test-process memory only. Every synthetic actor first signs in through real HTTPS. Local mode uses an isolated Caddy container namespace. */
export async function openSyntheticSession(page: Page, user: "browser-work-notes" | "browser-work-debrief" | "browser-work-export" | "browser-work-meeting") {
  const hosted = process.env.COMPOSE_PROJECT_NAME === "butler-ci";
  const isolatedLocal = process.platform === "linux" && process.env.BUTLER_LOCAL_REAL_UI_TESTS === "1" && process.env.BUTLER_LOCAL_BROWSER_NAMESPACE === "isolated-caddy" && process.env.COMPOSE_PROJECT_NAME === "butler-meeting-local" && process.env.BUTLER_E2E_ORIGIN === "https://localhost:8443";
  if (process.env.BUTLER_ENV !== "test" || process.env.BUTLER_POSTGRES_DB !== "butler_test_container" || (!hosted && !isolatedLocal)) throw new Error("Explicit disposable browser environment required");
  const cookies = sessions.get(user);
  if (cookies) await page.context().addCookies(cookies);
  await page.goto("/");
  if (!cookies) {
    await page.getByLabel("Username", { exact: true }).fill(user);
    await page.getByLabel("Password", { exact: true }).fill("synthetic-browser-password-only-0123456789");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("region", { name: "Your session", exact: true })).toBeVisible();
    sessions.set(user, await page.context().cookies());
  }
}
