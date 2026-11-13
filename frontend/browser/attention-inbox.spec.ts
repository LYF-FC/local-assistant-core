import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";
import { task } from "../src/test-support/tasks";
import { approval, approvalPage, doc, documentPage, filingPage, filingRow, notificationPage, notificationRow, reminderPage, reminderRow, scope, SECRET, stamp, taskPage, uid } from "../src/test-support/attention";

type Handler = (body: Record<string, unknown>) => { status?: number; json?: unknown } | undefined;
const READ_PATHS = ["/api/v1/approvals/query", "/api/v1/documents/query", "/api/v1/filing/query", "/api/v1/notifications/query", "/api/v1/reminders/query", "/api/v1/tasks/query"];
const answer = (path: string, body: Record<string, unknown>) => ({
  "/api/v1/approvals/query": approvalPage([approval(1), approval(2)]),
  "/api/v1/filing/query": filingPage(String(body.state), body.state === "failed" ? [filingRow(11, "failed")] : []),
  "/api/v1/notifications/query": notificationPage(String(body.state), body.state === "unknown" ? [notificationRow(21, "unknown")] : []),
  "/api/v1/documents/query": documentPage([doc()]),
  "/api/v1/reminders/query": reminderPage([reminderRow()]),
  "/api/v1/tasks/query": taskPage([{ ...task, owner_id: "22222222-2222-4222-8222-222222222222", scope, due_at: stamp }]),
})[path];

async function mock(page: Page, handlers: Record<string, Handler> = {}) {
  const calls: { method: string; path: string; body: Record<string, unknown>; csrf: string | undefined }[] = [];
  const other: string[] = [];
  await page.route("**/api/**", async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (!READ_PATHS.includes(path) || request.method() !== "POST") { other.push(`${request.method()} ${path}`); return route.fulfill({ status: 404, json: { detail: "Unexpected request" } }); }
    const body = request.postDataJSON() as Record<string, unknown>;
    calls.push({ method: request.method(), path, body, csrf: request.headers()["x-csrf-token"] });
    const key = `${path}:${String(body.state ?? "")}`;
    const override = (handlers[key] ?? handlers[path])?.(body);
    if (override) return route.fulfill({ status: override.status ?? 200, json: override.json ?? { detail: "x" } });
    return route.fulfill({ json: answer(path, body) });
  });
  return { calls, other };
}
const panel = (page: Page) => page.getByRole("region", { name: "Attention inbox", exact: true });
const refresh = (page: Page) => panel(page).getByRole("button", { name: "Refresh inbox", exact: true }).click();
async function open(page: Page) { await page.goto("/test-harness/inbox.html"); }

test("reads nothing until refresh, then composes eight read-only queries without approval controls", async ({ page }) => {
  const { calls, other } = await mock(page);
  await open(page);
  await expect(panel(page).getByRole("status").first()).toContainText("Nothing is read until you do.");
  expect(calls).toHaveLength(0);
  await refresh(page);
  await expect(panel(page).getByRole("status").first()).toContainText("Inbox loaded.");
  expect(calls).toHaveLength(8);
  expect(calls.every(call => call.method === "POST" && call.csrf?.startsWith("synthetic-component-csrf-"))).toBe(true);
  expect(other).toEqual([]);
  expect(new Set(calls.map(call => call.path))).toEqual(new Set(READ_PATHS));
  const approvals = panel(page).getByRole("region", { name: "Pending approvals", exact: true });
  await expect(approvals).toContainText("Requested by you");
  await expect(approvals).toContainText("Requested by another member of this scope");
  await expect(approvals).toContainText("Awaiting a decision");
  await expect(approvals).toContainText("No approvals screen is available in this release");
  await expect(approvals.getByRole("button")).toHaveCount(0);
  await expect(panel(page)).not.toContainText(SECRET);
  await expect(panel(page)).not.toContainText("payload_hash");
  await expect(panel(page).getByRole("region", { name: "Failures: filing", exact: true })).toContainText("Filing failed");
  await expect(panel(page).getByRole("region", { name: "Failures: notifications", exact: true })).toContainText("Delivery not confirmed");
  await expect(panel(page).getByRole("region", { name: "Documents needing review", exact: true })).toContainText("Text review needed");
  await expect(panel(page).getByRole("region", { name: "Delivered reminders", exact: true })).toContainText("Delivered, not acknowledged");
  await expect(panel(page).getByRole("region", { name: "Overdue open tasks", exact: true })).toContainText("Open, overdue");
  expect(page.url()).toMatch(/inbox\.html$/);
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).toBe('{"local":{},"session":{}}');
  expect(await page.evaluate(async () => (await navigator.serviceWorker?.getRegistrations?.())?.length ?? 0)).toBe(0);
});

test("is usable on a phone and by keyboard", async ({ page }, testInfo) => {
  await mock(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await refresh(page);
  await expect(panel(page).getByRole("status").first()).toContainText("Inbox loaded.");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("attention-inbox-mobile.png"), fullPage: true });
  const button = panel(page).getByRole("button", { name: /^Open task:/ });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Navigation record")).toHaveAttribute("data-opened", /"kind":"task"/);
});

test("opens records with only minimal coordinates", async ({ page }) => {
  await mock(page);
  await open(page);
  await refresh(page);
  await panel(page).getByRole("button", { name: /^Open task:/ }).click();
  await panel(page).getByRole("button", { name: /^Open document:/ }).click();
  await panel(page).getByRole("button", { name: /^Open reminder:/ }).click();
  const opened = JSON.parse((await page.getByLabel("Navigation record").getAttribute("data-opened"))!);
  expect(opened[0]).toEqual({ type: "source", target: { kind: "task", id: task.id, owner_id: "22222222-2222-4222-8222-222222222222", scope, revision: task.revision, created_at: task.created_at } });
  expect(opened[1]).toMatchObject({ type: "source", target: { kind: "document", id: uid(50), scope, revision: 3 } });
  expect(opened[2]).toEqual({ type: "destination", destination: { view: "reminders", scope } });
  expect(JSON.stringify(opened)).not.toMatch(/Synthetic review|title|content_text|payload/);
  await panel(page).getByRole("button", { name: "Search records", exact: true }).click();
  await expect(page.getByLabel("Navigation record")).toHaveAttribute("data-searched", "1");
});

test("a failed source is unavailable, never empty, and retry re-reads only that source", async ({ page }) => {
  const { calls } = await mock(page, { "/api/v1/filing/query:unknown": () => ({ status: 503, json: { detail: "secret provider traceback" } }) });
  await open(page);
  await refresh(page);
  await expect(panel(page).getByRole("status").first()).toContainText("Inbox loaded.");
  const filing = panel(page).getByRole("region", { name: "Failures: filing", exact: true });
  await expect(filing).toContainText("Unavailable: filing with unconfirmed outcome. This is not an empty result.");
  await expect(panel(page)).not.toContainText("traceback");
  await expect(panel(page)).not.toContainText("Nothing needs attention in the sources that loaded.");
  expect(calls).toHaveLength(8);
  const second = await mock(page);
  await filing.getByRole("button", { name: "Retry filing with unconfirmed outcome", exact: true }).click();
  await expect(panel(page).getByRole("status").first()).toContainText("Re-read filing with unconfirmed outcome only.");
  await expect(filing).not.toContainText("Unavailable");
  expect(second.calls).toHaveLength(1);
  expect(second.calls[0]).toMatchObject({ path: "/api/v1/filing/query", body: { state: "unknown" } });
});

test("says nothing needs attention only when every source loaded and none matched", async ({ page }) => {
  const empty: Record<string, Handler> = {
    "/api/v1/approvals/query": () => ({ json: approvalPage([]) }), "/api/v1/documents/query": () => ({ json: documentPage([]) }),
    "/api/v1/reminders/query": () => ({ json: reminderPage([]) }), "/api/v1/tasks/query": () => ({ json: taskPage([]) }),
    "/api/v1/filing/query": body => ({ json: filingPage(String(body.state)) }), "/api/v1/notifications/query": body => ({ json: notificationPage(String(body.state)) }),
  };
  await mock(page, empty);
  await open(page);
  await refresh(page);
  await expect(panel(page)).toContainText("Nothing needs attention in the sources that loaded.");
  await mock(page, { ...empty, "/api/v1/tasks/query": () => ({ status: 500 }) });
  await refresh(page);
  await expect(panel(page)).toContainText("Some sources are unavailable. Nothing is shown for them, which does not mean nothing needs attention.");
  await expect(panel(page)).not.toContainText("Nothing needs attention in the sources that loaded.");
});

test.describe("authorization denial", () => {
  for (const status of [401, 403, 404, 410]) {
    test(`clears every section on ${status}`, async ({ page }) => {
      await mock(page, { "/api/v1/tasks/query": () => ({ status }) });
      await open(page);
      await refresh(page);
      await expect(panel(page).getByRole("status").first()).toContainText("Inbox access is no longer available");
      await expect(panel(page).getByRole("region")).toHaveCount(0);
      await expect(panel(page)).not.toContainText("Approval request");
      await expect(page.getByLabel("Navigation record")).toHaveAttribute("data-signed-out", status === 401 ? "1" : "0");
    });
  }
});

test("clears on expiry, hidden tab and scope change, and never reads again by itself", async ({ page }) => {
  await page.clock.install({ time: Date.now() });
  const { calls } = await mock(page);
  await open(page);
  await refresh(page);
  await expect(panel(page).getByRole("region", { name: "Pending approvals", exact: true })).toBeVisible();
  await page.clock.fastForward(61_000);
  await expect(panel(page).getByRole("status").first()).toContainText("This inbox expired. Refresh to see current items.");
  await expect(panel(page).getByRole("region")).toHaveCount(0);
  expect(calls).toHaveLength(8);
  await refresh(page);
  await expect(panel(page).getByRole("region", { name: "Pending approvals", exact: true })).toBeVisible();
  await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, value: true }); document.dispatchEvent(new Event("visibilitychange")); });
  await expect(panel(page).getByRole("status").first()).toContainText("Inbox hidden.");
  await expect(panel(page).getByRole("region")).toHaveCount(0);
  await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, value: false }); });
  await refresh(page);
  await expect(panel(page).getByRole("region", { name: "Pending approvals", exact: true })).toBeVisible();
  expect(calls).toHaveLength(24);
  await panel(page).getByRole("combobox", { name: "Inbox scope", exact: true }).selectOption("household_shared");
  await expect(panel(page).getByRole("status").first()).toContainText("Scope changed. Refresh to read current records.");
  await expect(panel(page).getByRole("region")).toHaveCount(0);
  await page.waitForTimeout(250);
  expect(calls).toHaveLength(24);
});

test("the soonest approval expiry ends the view early", async ({ page }) => {
  await page.clock.install({ time: Date.now() });
  await mock(page, { "/api/v1/approvals/query": () => ({ json: approvalPage([approval(1, { expires_at: new Date(Date.now() + 15_000).toISOString() })]) }) });
  await open(page);
  await refresh(page);
  await expect(panel(page).getByRole("region", { name: "Pending approvals", exact: true })).toBeVisible();
  await page.clock.fastForward(16_000);
  await expect(panel(page).getByRole("status").first()).toContainText("This inbox expired.");
  await expect(panel(page).getByRole("region")).toHaveCount(0);
});

test("no request other than the six read routes is ever sent", async ({ page }) => {
  const { calls, other } = await mock(page);
  await open(page);
  await refresh(page);
  await panel(page).getByRole("button", { name: /^Open task:/ }).click();
  await refresh(page);
  expect(other).toEqual([]);
  expect(calls.every(call => READ_PATHS.includes(call.path) && call.method === "POST")).toBe(true);
  expect(calls.some(call => /decide|cancel|consume|approvals\/[0-9a-f-]{36}/.test(call.path))).toBe(false);
});
