import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const password = "synthetic-browser-password-only-0123456789";
async function login(page: Page, slug: string) {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(slug);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("region", { name: "Your session" })).toBeVisible();
}
function mutate(action: string) {
  execFileSync("docker", ["compose", "-f", resolve("../infra/core/compose.yml"), "run", "--rm", "-T", "migrate", "python", "-", action], { input: readFileSync(resolve("../scripts/browser-fixtures.py")), stdio: ["pipe", "pipe", "pipe"] });
}
test("secure cookie, reload bootstrap, no persisted tokens and sign-out", async ({ page, context }) => {
  await login(page, "browser-flow");
  const cookies = await context.cookies();
  const cookie = cookies.find(c => c.name === "__Host-butler_session");
  expect(cookie).toMatchObject({ secure: true, httpOnly: true, sameSite: "Strict", path: "/" });
  expect(cookie?.expires).toBeGreaterThan(Date.now() / 1000);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookie: document.cookie }))).toEqual({ local: 0, session: 0, cookie: "" });
  await page.reload();
  await expect(page.getByRole("region", { name: "Your session" })).toBeVisible();
  await expect(page.getByText("household_shared", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("form", { name: "Sign in" })).toBeVisible();
  expect((await context.cookies()).some(c => c.name === "__Host-butler_session")).toBe(false);
  await page.reload();
  await expect(page.getByRole("form", { name: "Sign in" })).toBeVisible();
});
test("HTTP offers no credential form and invalid CSRF is denied", async ({ page, context }) => {
  const plain = await context.newPage();
  await plain.goto(process.env.BUTLER_E2E_HTTP_ORIGIN!);
  await expect(plain.getByText("Open the HTTPS address shown by setup to sign in securely.")).toBeVisible();
  await expect(plain.getByLabel("Password", { exact: true })).toHaveCount(0);
  await login(page, "browser-policy");
  const status = await page.evaluate(async () => (await fetch("/api/v1/auth/logout", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": "invalid" }, body: "{}" })).status);
  expect(status).toBe(403);
  await page.getByRole("button", { name: "Refresh session" }).click();
  await expect(page.getByRole("region", { name: "Your session" })).toBeVisible();
});
test("current scope and disabled identity are reflected on refresh", async ({ page }) => {
  await login(page, "browser-revoked");
  await expect(page.getByText("household_shared", { exact: true })).toBeVisible();
  mutate("revoke");
  await page.getByRole("button", { name: "Refresh session" }).click();
  await expect(page.getByText("household_shared", { exact: true })).toHaveCount(0);
  mutate("disable");
  await page.getByRole("button", { name: "Refresh session" }).click();
  await expect(page.getByRole("form", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Your session" })).toHaveCount(0);
});
