import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";
import { auditCategories, auditExcludes } from "../src/operations-api";

const ACTOR = "33333333-3333-4333-8333-333333333333", T0 = Date.parse("2026-11-10T12:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString().replace(".000Z", "Z");
const windows = { "24h": 86400000, "7d": 604800000 } as const;
// The parser pins valid_until to checked_at + 60 s, so every fixture is built from the fake clock.
function summary(window: keyof typeof windows, success: number) {
  return { schema_version: 1, scope: "technical_admin", actor_id: ACTOR, checked_at: iso(T0), valid_until: iso(T0 + 60000), window, window_start: iso(T0 - windows[window]), window_end: iso(T0),
    categories: auditCategories.map((key, i) => ({ key, success: i === 0 ? success : 0, denied: i === 1 ? 2 : 0, other: 0 })), totals: { success, denied: 2, other: 0 }, excludes: [...auditExcludes] };
}
type Held = { body: Record<string, unknown>; release: (status?: number, json?: unknown) => void };
async function mock(page: Page, plan: (call: number, body: Record<string, unknown>) => { status?: number; json?: unknown } | "hold") {
  const calls: Record<string, unknown>[] = [], held: Held[] = [], other: string[] = [];
  await page.route("**/api/**", async (route: Route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path !== "/api/v1/operations/audit-summary" || request.method() !== "POST") { other.push(`${request.method()} ${path}`); return route.fulfill({ status: 404, json: { detail: "Unexpected request" } }); }
    const body = request.postDataJSON() as Record<string, unknown>;
    calls.push(body);
    const decision = plan(calls.length, body);
    if (decision === "hold") return new Promise<void>(resolve => held.push({ body, release: (status = 200, json = summary("24h", 99)) => { void route.fulfill({ status, json }).catch(() => undefined); resolve(); } }));
    return route.fulfill({ status: decision.status ?? 200, json: decision.json });
  });
  return { calls, held, other };
}
const section = (page: Page) => page.getByRole("region", { name: "Audit summary", exact: true });
const status = (page: Page) => section(page).getByRole("status");
const table = (page: Page) => section(page).getByRole("table", { name: "Audit event counts" });
const load = (page: Page) => section(page).getByRole("button", { name: "Load audit summary", exact: true }).click();
const setHidden = (page: Page, hidden: boolean) => page.evaluate(value => { Object.defineProperty(document, "hidden", { configurable: true, get: () => value }); document.dispatchEvent(new Event("visibilitychange")); }, hidden);
async function open(page: Page) {
  await page.clock.install({ time: T0 });
  await page.goto("/test-harness/audit.html");
  await expect(status(page)).toContainText("Load the audit summary");
}
const signedOut = (page: Page) => page.getByLabel("Navigation record").getAttribute("data-signed-out");

test("reads nothing until the explicit load, then shows exactly the counted table", async ({ page }) => {
  const { calls, other } = await mock(page, () => ({ json: summary("24h", 5) }));
  await open(page);
  await page.clock.fastForward(30000);
  expect(calls).toHaveLength(0);
  await load(page);
  await expect(table(page)).toBeVisible();
  await expect(table(page).getByRole("row", { name: /Total/ })).toContainText("5");
  expect(calls).toEqual([{ scope: "technical_admin", window: "24h" }]);
  expect(other).toEqual([]);
});

test("clears the summary when the tab becomes hidden and does not restore it on return", async ({ page }) => {
  const { calls } = await mock(page, () => ({ json: summary("24h", 5) }));
  await open(page);
  await load(page);
  await expect(table(page)).toBeVisible();
  await setHidden(page, true);
  await expect(table(page)).toHaveCount(0);
  await expect(status(page)).toContainText("Audit summary hidden");
  await setHidden(page, false);
  await expect(table(page)).toHaveCount(0);
  expect(calls).toHaveLength(1);
});

test("clears at the 60-second validity limit and never refreshes by itself", async ({ page }) => {
  const { calls } = await mock(page, () => ({ json: summary("24h", 5) }));
  await open(page);
  await load(page);
  await expect(table(page)).toBeVisible();
  await page.clock.fastForward(59000);
  await expect(table(page)).toBeVisible();
  await page.clock.fastForward(2000);
  await expect(table(page)).toHaveCount(0);
  await expect(status(page)).toContainText("Audit summary expired");
  await page.clock.fastForward(300000);
  expect(calls).toHaveLength(1);
});

test("a response arriving after the tab was hidden is discarded", async ({ page }) => {
  const { held } = await mock(page, () => "hold");
  await open(page);
  await load(page);
  await expect.poll(() => held.length).toBe(1);
  await setHidden(page, true);
  await expect(status(page)).toContainText("Audit summary hidden");
  held[0].release(200, summary("24h", 77));
  await page.waitForTimeout(200);
  await setHidden(page, false);
  await expect(table(page)).toHaveCount(0);
  await expect(section(page).getByRole("button", { name: "Load audit summary" })).toBeEnabled();
});

test("a response arriving after the expiry cleared the request is discarded", async ({ page }) => {
  const { held } = await mock(page, () => "hold");
  await open(page);
  await load(page);
  await expect.poll(() => held.length).toBe(1);
  await page.clock.fastForward(61000);
  await expect(status(page)).toContainText("Audit summary expired");
  held[0].release(200, summary("24h", 77));
  await page.waitForTimeout(200);
  await expect(table(page)).toHaveCount(0);
  await expect(status(page)).toContainText("Audit summary expired");
});

test("a late response from a superseded request never replaces the newer summary", async ({ page }) => {
  const { held, calls } = await mock(page, call => call === 1 ? "hold" : { json: summary("24h", 5) });
  await open(page);
  await load(page);
  await expect.poll(() => held.length).toBe(1);
  await setHidden(page, true);
  await setHidden(page, false);
  await load(page);
  await expect(table(page).getByRole("row", { name: /Total/ })).toContainText("5");
  held[0].release(200, summary("24h", 77));
  await page.waitForTimeout(200);
  await expect(table(page).getByRole("row", { name: /Total/ })).toContainText("5");
  await expect(table(page)).not.toContainText("77");
  expect(calls).toHaveLength(2);
});

test("an unavailable response shows a sanitized message with no counts and a retry succeeds", async ({ page }) => {
  const { calls } = await mock(page, call => call === 1 ? { status: 503, json: { detail: "synthetic-secret traceback" } } : { json: summary("24h", 5) });
  await open(page);
  await load(page);
  await expect(status(page)).not.toContainText(/synthetic-secret|traceback/);
  await expect(table(page)).toHaveCount(0);
  await expect(section(page).getByRole("button", { name: "Load audit summary" })).toBeEnabled();
  await page.clock.fastForward(20000);
  expect(calls).toHaveLength(1);
  await load(page);
  await expect(table(page)).toBeVisible();
  expect(calls).toHaveLength(2);
});

test("an invalid payload is refused without inferring counts, and a 401 signs the session out once", async ({ page }) => {
  const bad = { ...summary("24h", 5), actor_id: "44444444-4444-4444-8444-444444444444" };
  const { calls } = await mock(page, call => call === 1 ? { json: bad } : { status: 401, json: { detail: "x" } });
  await open(page);
  await load(page);
  await expect(status(page)).toContainText("unavailable or invalid");
  await expect(table(page)).toHaveCount(0);
  expect(await signedOut(page)).toBe("0");
  await load(page);
  await expect.poll(() => signedOut(page)).toBe("1");
  await expect(table(page)).toHaveCount(0);
  expect(calls).toHaveLength(2);
});

test("a window change clears the summary, and no browser storage or cookie is written", async ({ page }) => {
  const { calls } = await mock(page, (_call, body) => ({ json: summary(body.window as "24h" | "7d", 5) }));
  await open(page);
  await load(page);
  await expect(table(page)).toBeVisible();
  await section(page).getByLabel("Audit summary window").selectOption("7d");
  await expect(table(page)).toHaveCount(0);
  await load(page);
  await expect(table(page)).toBeVisible();
  expect(calls).toEqual([{ scope: "technical_admin", window: "24h" }, { scope: "technical_admin", window: "7d" }]);
  const stored = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookie: document.cookie }));
  expect(stored).toEqual({ local: 0, session: 0, cookie: "" });
});
