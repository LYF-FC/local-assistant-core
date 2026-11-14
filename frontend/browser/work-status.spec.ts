// Spec 073 test 22: mocked component tests for WorkStatusSection. Mocked API, local opt-in only;
// not hosted CI evidence and not real-stack evidence (see e2e/calendars.spec.ts for that).
import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";
import { workExcludes, workNotObserved, workQueues } from "../src/operations-api";

const ACTOR = "33333333-3333-4333-8333-333333333333", T0 = Date.parse("2026-11-10T12:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString().replace(".000Z", "Z");
const NOTIFICATION_OVERDUE = "Notification queue work (queuing, processing or reconciling a delivery) has waited longer than the grace period. This does not mean a notification will be sent: a queued delivery may still be paused, deferred or cancelled.";
const PROHIBITED = ["unsent", "pending send", "missed notification", "will be delivered"];
// The parser pins valid_until to checked_at + 60 s, so every fixture is built from the fake clock.
function work(states: string[] = ["stalled", "overdue", "overdue", "none_observed"]) {
  return { schema_version: 1, scope: "technical_admin", actor_id: ACTOR, checked_at: iso(T0), valid_until: iso(T0 + 60000),
    queues: workQueues.map((key, i) => ({ key, state: states[i] })), not_observed: [...workNotObserved], excludes: [...workExcludes] };
}
type Held = { release: (status?: number, json?: unknown) => void };
async function mock(page: Page, plan: (call: number) => { status?: number; json?: unknown } | "hold") {
  const calls: Record<string, unknown>[] = [], held: Held[] = [], other: string[] = [];
  await page.route("**/api/**", async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path !== "/api/v1/operations/work-status" || request.method() !== "POST") { other.push(`${request.method()} ${path}`); return route.fulfill({ status: 404, json: { detail: "Unexpected request" } }); }
    calls.push(request.postDataJSON() as Record<string, unknown>);
    const decision = plan(calls.length);
    if (decision === "hold") return new Promise<void>(resolve => held.push({ release: (status = 200, json = work(["overdue", "overdue", "overdue", "overdue"])) => { void route.fulfill({ status, json }).catch(() => undefined); resolve(); } }));
    return route.fulfill({ status: decision.status ?? 200, json: decision.json });
  });
  return { calls, held, other };
}
const section = (page: Page) => page.getByRole("region", { name: "Work status", exact: true });
const status = (page: Page) => section(page).getByRole("status");
const queues = (page: Page) => section(page).getByRole("list", { name: "Queue states" });
const load = (page: Page) => section(page).getByRole("button", { name: "Load work status", exact: true }).click();
const setHidden = (page: Page, hidden: boolean) => page.evaluate(value => { Object.defineProperty(document, "hidden", { configurable: true, get: () => value }); document.dispatchEvent(new Event("visibilitychange")); }, hidden);
async function open(page: Page) {
  await page.clock.install({ time: T0 });
  await page.goto("/test-harness/work-status.html");
  await expect(status(page)).toContainText("Load work status");
}
const signedOut = (page: Page) => page.getByLabel("Navigation record").getAttribute("data-signed-out");

test("reads nothing until the explicit load, then shows queue states with the exact copy", async ({ page }) => {
  const { calls, other } = await mock(page, () => ({ json: work() }));
  await open(page);
  await page.clock.fastForward(30000);
  expect(calls).toHaveLength(0);
  await load(page);
  await expect(queues(page)).toBeVisible();
  await expect(queues(page)).toContainText("Approved jobs: An attempt or lease expired and was not taken over.");
  await expect(queues(page)).toContainText("Reminders: Eligible work has waited longer than the grace period.");
  await expect(queues(page).getByRole("listitem").nth(2)).toContainText(NOTIFICATION_OVERDUE);
  await expect(queues(page)).toContainText("Filing: No overdue or stalled work was observed. This is not a worker health check.");
  await expect(section(page).getByRole("list", { name: "Not observed queues" })).toContainText("Calendar sync: Not observed by this view.");
  const text = (await section(page).innerText()).toLowerCase();
  for (const phrase of PROHIBITED) expect(text).not.toContain(phrase);
  expect(calls).toEqual([{ scope: "technical_admin" }]);
  expect(other).toEqual([]);
  await page.clock.fastForward(50000);
  expect(calls).toHaveLength(1);
});

test("clears when the tab becomes hidden and does not restore on return", async ({ page }) => {
  const { calls } = await mock(page, () => ({ json: work() }));
  await open(page);
  await load(page);
  await expect(queues(page)).toBeVisible();
  await setHidden(page, true);
  await expect(queues(page)).toHaveCount(0);
  await expect(status(page)).toContainText("Work status hidden");
  await setHidden(page, false);
  await expect(queues(page)).toHaveCount(0);
  expect(calls).toHaveLength(1);
});

test("clears at the 60-second validity limit and never refreshes by itself", async ({ page }) => {
  const { calls } = await mock(page, () => ({ json: work() }));
  await open(page);
  await load(page);
  await expect(queues(page)).toBeVisible();
  await page.clock.fastForward(59000);
  await expect(queues(page)).toBeVisible();
  await page.clock.fastForward(2000);
  await expect(queues(page)).toHaveCount(0);
  await expect(status(page)).toContainText("Work status expired");
  await page.clock.fastForward(300000);
  expect(calls).toHaveLength(1);
});

test("a response arriving after the tab was hidden is discarded", async ({ page }) => {
  const { held } = await mock(page, () => "hold");
  await open(page);
  await load(page);
  await expect.poll(() => held.length).toBe(1);
  await setHidden(page, true);
  await expect(status(page)).toContainText("Work status hidden");
  held[0].release();
  await page.waitForTimeout(200);
  await setHidden(page, false);
  await expect(queues(page)).toHaveCount(0);
});

test("a response arriving after the expiry cleared the request is discarded", async ({ page }) => {
  const { held } = await mock(page, () => "hold");
  await open(page);
  await load(page);
  await expect.poll(() => held.length).toBe(1);
  await page.clock.fastForward(61000);
  await expect(status(page)).toContainText("Work status expired");
  held[0].release();
  await page.waitForTimeout(200);
  await expect(queues(page)).toHaveCount(0);
});

test("a late response from a superseded request never replaces the newer one", async ({ page }) => {
  const { held, calls } = await mock(page, call => call === 1 ? "hold" : { json: work(["none_observed", "none_observed", "none_observed", "none_observed"]) });
  await open(page);
  await load(page);
  await expect.poll(() => held.length).toBe(1);
  await setHidden(page, true);
  await setHidden(page, false);
  await load(page);
  await expect(queues(page)).toContainText("Approved jobs: No overdue or stalled work was observed.");
  held[0].release();
  await page.waitForTimeout(200);
  await expect(queues(page)).not.toContainText("has waited longer");
  expect(calls).toHaveLength(2);
});

test("an unavailable response shows no states and an explicit retry works", async ({ page }) => {
  const { calls } = await mock(page, call => call === 1 ? { status: 503, json: { detail: "synthetic-secret traceback" } } : { json: work() });
  await open(page);
  await load(page);
  await expect(status(page)).toContainText("Work status unavailable");
  await expect(status(page)).not.toContainText(/synthetic-secret|traceback/);
  await expect(queues(page)).toHaveCount(0);
  await page.clock.fastForward(20000);
  expect(calls).toHaveLength(1);
  await load(page);
  await expect(queues(page)).toBeVisible();
  expect(calls).toHaveLength(2);
});

test("an invalid payload shows nothing and a 401 signs out once", async ({ page }) => {
  const bad = { ...work(), queues: [...work().queues.slice(0, 3), { key: "filing", state: "overdue", count: 4 }] };
  const { calls } = await mock(page, call => call === 1 ? { json: bad } : { status: 401, json: { detail: "x" } });
  await open(page);
  await load(page);
  await expect(status(page)).toContainText("unavailable or invalid");
  await expect(queues(page)).toHaveCount(0);
  expect(await signedOut(page)).toBe("0");
  await load(page);
  await expect.poll(() => signedOut(page)).toBe("1");
  await expect(queues(page)).toHaveCount(0);
  expect(calls).toHaveLength(2);
});

test("no browser storage or cookie is written", async ({ page }) => {
  await mock(page, () => ({ json: work() }));
  await open(page);
  await load(page);
  await expect(queues(page)).toBeVisible();
  const stored = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookie: document.cookie }));
  expect(stored).toEqual({ local: 0, session: 0, cookie: "" });
});
