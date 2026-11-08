import { openSyntheticSession } from "./work-browser-session";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test.skip(process.env.BUTLER_WORK_NOTES_BROWSER_TESTS !== "1", "Optional synthetic interface overlay required");
function apply(module: string, id: string) {
  if (process.env.BUTLER_ENV !== "test" || process.env.BUTLER_POSTGRES_DB !== "butler_test_container" || process.env.COMPOSE_PROJECT_NAME !== "butler-ci") throw new Error("Disposable CI executor only");
  execFileSync("docker", ["compose", "-f", "infra/core/compose.yml", "run", "--rm", "-T", "migrate", "python", "-m", module, "--environment", "test", "--request", id], { cwd: resolve(process.cwd(), ".."), env: process.env, timeout: 45000, stdio: "pipe" });
}
async function open(page: Page) {
  await openSyntheticSession(page, "browser-work-debrief");
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Work Companion", exact: true }).click();
  await page.getByRole("button", { name: "Load assigned workspaces", exact: true }).click();
  await page.getByRole("button", { name: "synthetic-adapter-ci", exact: true }).click();
  const panel = page.getByRole("region", { name: "Synthetic Work notes", exact: true });
  await panel.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  await expect(panel.getByRole("button", { name: "New sample debrief", exact: true })).toBeEnabled();
  return panel;
}
async function prepare(page: Page, text: string) {
  await page.getByRole("button", { name: "New sample debrief", exact: true }).click();
  await page.getByLabel("Sample debrief", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Prepare proposals", exact: true }).click();
  return page.getByRole("region", { name: "Sample debrief review", exact: true });
}
async function options(page: Page) {
  const form = page.getByRole("form", { name: "New sample note", exact: true });
  await form.getByRole("checkbox", { name: "container-adapter", exact: true }).check();
  await form.getByLabel("Retention policy", { exact: true }).selectOption({ index: 1 });
  await form.getByLabel("Keep until", { exact: true }).selectOption("3600");
  return form;
}

test("labelled debrief prepares without writes and explicitly saves two reviewed proposals", async ({ page }) => {
  test.setTimeout(90000);
  const panel = await open(page);
  let writes = 0;
  page.on("request", request => { if (request.url().endsWith("/captures")) writes++; });
  const debrief = await prepare(page, "Action: Prepare the sample agenda\n\nQuestion: Clarify the sample dependency\nDecision: Keep the sample review\nObservation: Omit this sample");
  await expect(debrief.getByRole("listitem")).toHaveCount(4);
  expect(writes).toBe(0);
  await debrief.getByRole("button", { name: "Omit line 5", exact: true }).click();
  await expect(debrief.getByRole("listitem")).toHaveCount(3);
  await expect(debrief).not.toContainText("Omit this sample");
  await debrief.getByRole("button", { name: "Review line 1", exact: true }).click();
  const form = await options(page);
  await expect(form.getByLabel("Note type", { exact: true })).toHaveValue("action");
  await expect(form.getByLabel("Owner", { exact: true })).toHaveValue("unknown");
  await expect(form.getByLabel("Due date", { exact: true })).toHaveValue("");
  await form.getByLabel("Sample note", { exact: true }).fill("Edited sample agenda");
  await expect(debrief.getByRole("listitem", { name: "Debrief line 1", exact: true }).locator("blockquote")).toContainText("Action: Prepare the sample agenda");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/work-debrief-mobile.png", fullPage: true });
  const prepared = page.waitForResponse(r => r.url().endsWith("/captures") && r.request().method() === "POST");
  await form.evaluate(element => { const form = element as HTMLFormElement; form.requestSubmit(); form.requestSubmit(); });
  const response = await prepared, capture = await response.json();
  expect(response.request().postDataJSON().draft).toMatchObject({ kind: "action", marker: "synthetic:Edited sample agenda", owner_id: null, due_at: null });
  expect(response.request().postData()).not.toContain("Clarify the sample dependency");
  await expect(debrief.getByRole("listitem", { name: "Debrief line 1", exact: true })).toContainText("Draft save awaiting processing");
  await expect(debrief.getByRole("button", { name: "Review line 3", exact: true })).toBeDisabled();
  apply("app.work_capture_worker", capture.capture_preparation_id);
  await panel.getByRole("button", { name: "Recover or refresh request status", exact: true }).click();
  await expect(debrief.getByRole("listitem", { name: "Debrief line 1", exact: true })).toContainText("Draft save applied");
  await expect(debrief.getByRole("listitem", { name: "Debrief line 3", exact: true })).toContainText("Not requested");
  await panel.getByRole("button", { name: "Open resulting note", exact: true }).click();
  const detail = panel.getByRole("region", { name: "Selected work note", exact: true });
  await expect(detail).toContainText("Edited sample agenda");
  await expect(detail).toContainText("action · draft");
  const confirmed = page.waitForResponse(r => r.url().endsWith("/confirm") && r.request().method() === "POST");
  await detail.getByRole("button", { name: "Confirm this version", exact: true }).click();
  apply("app.work_confirmation_worker", (await (await confirmed).json()).confirmation_request_id);
  await panel.getByRole("button", { name: "Recover or refresh request status", exact: true }).click();
  await panel.getByRole("button", { name: "Open resulting note", exact: true }).click();
  await expect(detail).toContainText("action · confirmed");
  await debrief.getByRole("button", { name: "Review line 3", exact: true }).click();
  const second = await options(page);
  await expect(second.getByLabel("Sample note", { exact: true })).toHaveValue("Clarify the sample dependency");
  await expect(second.getByLabel("Note type", { exact: true })).toHaveValue("question");
  const preparedSecond = page.waitForResponse(r => r.url().endsWith("/captures") && r.request().method() === "POST");
  await second.getByRole("button", { name: "Request save", exact: true }).click();
  apply("app.work_capture_worker", (await (await preparedSecond).json()).capture_preparation_id);
  await panel.getByRole("button", { name: "Recover or refresh request status", exact: true }).click();
  await expect(debrief.getByRole("listitem", { name: "Debrief line 3", exact: true })).toContainText("Draft save applied");
  await expect(debrief.getByRole("listitem", { name: "Debrief line 4", exact: true })).toContainText("Not requested");
  expect(writes).toBe(2);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: "test-results/work-debrief-desktop.png", fullPage: true });
  await debrief.getByRole("button", { name: "Discard debrief", exact: true }).click();
  await expect(debrief).toHaveCount(0);
  await expect(panel).not.toContainText("Prepare the sample agenda");
});

test("uncertain proposal stays nonce-bound and discard prevents late payload restoration", async ({ page }) => {
  test.setTimeout(60000);
  const panel = await open(page);
  const debrief = await prepare(page, "Action: Ambiguous debrief sentinel\nQuestion: Untouched debrief sentinel");
  await debrief.getByRole("button", { name: "Review line 1", exact: true }).click();
  const form = await options(page);
  let captureId = "", calls = 0;
  await page.route("**/api/v1/work/workspaces/*/captures", async route => {
    calls++; const response = await route.fetch(); captureId = (await response.json()).capture_preparation_id;
    await route.abort("failed");
  });
  await form.getByRole("button", { name: "Request save", exact: true }).click();
  await expect(debrief.getByRole("listitem", { name: "Debrief line 1", exact: true })).toContainText("Response uncertain");
  await expect(debrief.getByRole("button", { name: "Review line 2", exact: true })).toBeDisabled();
  await panel.getByRole("button", { name: "Recover or refresh request status", exact: true }).click();
  await expect(debrief.getByRole("listitem", { name: "Debrief line 1", exact: true })).toContainText("Draft save awaiting processing");
  await expect(debrief.getByRole("listitem", { name: "Debrief line 2", exact: true })).toContainText("Not requested");
  expect(calls).toBe(1);
  await debrief.getByRole("button", { name: "Discard debrief", exact: true }).click();
  await expect(panel.getByRole("button", { name: "Retry same request", exact: true })).toHaveCount(0);
  await expect(panel).not.toContainText("Ambiguous debrief sentinel");
  await expect(panel).not.toContainText("Untouched debrief sentinel");
  apply("app.work_capture_worker", captureId);
  await panel.getByRole("button", { name: "Recover or refresh request status", exact: true }).click();
  await expect(panel.getByRole("region", { name: "Request outcome", exact: true })).toContainText("Applied at version 1");
  await expect(debrief).toHaveCount(0);
  await expect(panel).not.toContainText("Ambiguous debrief sentinel");
});

test("expiry, denial and view changes clear debrief input quotes and editor", async ({ page }) => {
  await page.clock.install();
  const panel = await open(page);
  let debrief = await prepare(page, "Action: Expiring debrief sentinel");
  await debrief.getByRole("button", { name: "Review line 1", exact: true }).click();
  await page.clock.fastForward(61000);
  await expect(debrief).toHaveCount(0);
  await expect(panel.getByRole("form", { name: "New sample note", exact: true })).toHaveCount(0);
  await expect(panel).not.toContainText("Expiring debrief sentinel");
  await panel.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  debrief = await prepare(page, "Question: Denied debrief sentinel");
  await debrief.getByRole("button", { name: "Review line 1", exact: true }).click();
  const form = await options(page);
  await page.route("**/api/v1/work/workspaces/*/captures", route => route.fulfill({ status: 403, json: { detail: "Denied" } }));
  await form.getByRole("button", { name: "Request save", exact: true }).click();
  await expect(panel.getByRole("alert")).toBeVisible();
  await expect(debrief).toHaveCount(0);
  await expect(panel).not.toContainText("Denied debrief sentinel");
  await page.unroute("**/api/v1/work/workspaces/*/captures");
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Memory", exact: true }).click();
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Work Companion", exact: true }).click();
  await page.getByRole("button", { name: "Load assigned workspaces", exact: true }).click();
  await page.getByRole("button", { name: "synthetic-adapter-ci", exact: true }).click();
  await panel.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  await page.getByRole("button", { name: "New sample debrief", exact: true }).click();
  await page.getByLabel("Sample debrief", { exact: true }).fill("Action: Unsaved debrief sentinel");
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Memory", exact: true }).click();
  await expect(panel).toHaveCount(0);
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Work Companion", exact: true }).click();
  await expect(page.getByLabel("Sample debrief", { exact: true })).toHaveCount(0);
});
