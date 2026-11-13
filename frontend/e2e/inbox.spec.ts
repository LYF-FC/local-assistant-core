import { expect, test } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";
test.skip(process.env.BUTLER_INBOX_BROWSER_TESTS !== "1", "Requires the inbox fixture phase with a fresh login budget");

// Real stack: built UI, API under the restricted runtime role and PostgreSQL, a real login session
// and the synthetic records from scripts/inbox-browser-fixtures.py. The only injected fault is the
// documented network failure in the unavailable-source test.
const READ = new Set(["/api/v1/approvals/query", "/api/v1/tasks/query", "/api/v1/reminders/query", "/api/v1/documents/query", "/api/v1/filing/query", "/api/v1/notifications/query"]);
let cookies: Awaited<ReturnType<BrowserContext["cookies"]>> | null = null;
async function login(page: Page) {
  if (cookies) {
    await page.context().addCookies(cookies);
    const restored = page.waitForResponse(r => r.url().endsWith("/api/v1/auth/session") && r.request().method() === "POST");
    await page.goto("/");
    await restored;
  } else {
    await page.goto("/");
    await page.getByLabel("Username", { exact: true }).fill("browser-inbox-flow");
    await page.getByLabel("Password", { exact: true }).fill("synthetic-browser-password-only-0123456789");
    const response = page.waitForResponse(r => r.url().endsWith("/api/v1/auth/login") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await response;
    cookies = await page.context().cookies();
  }
  await expect(page.getByRole("region", { name: "Memory", exact: true })).toBeVisible();
}
function record(page: Page) {
  const seen: { method: string; path: string }[] = [];
  page.on("request", request => { const url = new URL(request.url()); if (url.pathname.startsWith("/api/")) seen.push({ method: request.method(), path: url.pathname }); });
  return seen;
}
const panel = (page: Page) => page.getByRole("region", { name: "Attention inbox", exact: true });
const section = (page: Page, name: string) => panel(page).getByRole("region", { name, exact: true });
async function openInbox(page: Page) {
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Attention inbox", exact: true }).click();
  await expect(panel(page).getByRole("combobox", { name: /^Inbox scope/ }).locator("option")).toHaveText(["Member B — private"]);
  await expect(panel(page)).toContainText("Nothing is read until you do.");
}
const refresh = (page: Page) => panel(page).getByRole("button", { name: "Refresh inbox", exact: true }).click();

test("the real inbox loads every section with representative records and no approval controls", async ({ page }) => {
  await login(page);
  const seen = record(page);
  await openInbox(page);
  expect(seen.filter(r => READ.has(r.path))).toHaveLength(0);
  await refresh(page);
  await expect(panel(page)).toContainText("Inbox loaded.");
  await expect(section(page, "Overdue open tasks")).toContainText("Synthetic overdue inbox task");
  await expect(section(page, "Delivered reminders")).toContainText("Synthetic inbox delivered reminder");
  await expect(section(page, "Documents needing review")).toContainText("Synthetic inbox unreviewed document");
  await expect(section(page, "Documents needing review")).not.toContainText("Synthetic inbox filed document");
  await expect(section(page, "Failures: filing")).toContainText("Filing failed");
  await expect(section(page, "Failures: notifications")).toContainText("Delivery not confirmed");
  const approvals = section(page, "Pending approvals");
  await expect(approvals.getByRole("listitem")).toHaveCount(25);
  await expect(approvals).toContainText("No approvals screen is available in this release");
  // Evidence only: the only buttons in the approvals section load another page.
  await expect(approvals.getByRole("button")).toHaveCount(1);
  await expect(approvals.getByRole("button", { name: "Load more approvals", exact: true })).toBeVisible();
  const text = await panel(page).innerText();
  for (const hidden of ["SYNTHETIC-APPROVAL-PAYLOAD-MARKER", "synthetic-policy-1", "synthetic-other-member"]) expect(text).not.toContain(hidden);
  expect(await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage), url: location.href }))).toEqual({ local: [], session: [], url: new URL(page.url()).origin + "/" });
  await refresh(page);
  await expect(panel(page)).toContainText("Inbox loaded.");
  const api = seen.filter(r => READ.has(r.path) || r.path.includes("approvals") || /decide|cancel|consume|acknowledge|complete|retry|file/.test(r.path));
  expect(api.every(r => r.method === "POST" && READ.has(r.path))).toBe(true);
  expect(api.filter(r => r.path === "/api/v1/approvals/query")).toHaveLength(2);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("approvals page in the inbox through the real cursor and never mutate anything", async ({ page }) => {
  await login(page);
  const seen = record(page);
  await openInbox(page);
  await refresh(page);
  const approvals = section(page, "Pending approvals");
  await expect(approvals.getByRole("listitem")).toHaveCount(25);
  await expect(approvals).toContainText("More pending approvals exist than are shown");
  await approvals.getByRole("button", { name: "Load more approvals", exact: true }).click();
  await expect(approvals.getByRole("listitem")).toHaveCount(26);
  await expect(approvals).toContainText("Requested by another member of this scope");
  await expect(approvals).toContainText("Requested by you");
  await expect(approvals.getByRole("button", { name: "Load more approvals", exact: true })).toHaveCount(0);
  await expect(approvals).not.toContainText("More pending approvals exist");
  const queries = seen.filter(r => r.path === "/api/v1/approvals/query");
  expect(queries).toHaveLength(2);
  expect(seen.filter(r => r.method !== "GET" && !READ.has(r.path) && !r.path.startsWith("/api/v1/auth/"))).toEqual([]);
  expect(seen.some(r => /\/approvals\/[0-9a-f-]{36}|decide|cancel|consume/.test(r.path))).toBe(false);
  // Viewing and paging are read-only: the approval rows are untouched (checked against PostgreSQL by the CI script).
});

test("a failed source is shown as unavailable, never empty, and retries alone", async ({ page }) => {
  await login(page);
  await openInbox(page);
  let broken = true;
  await page.route("**/api/v1/documents/query", route => broken ? route.fulfill({ status: 500, json: { detail: "Synthetic injected source failure" } }) : route.continue());
  await refresh(page);
  const documents = section(page, "Documents needing review");
  await expect(documents).toContainText("Unavailable: documents needing review. This is not an empty result.");
  await expect(documents).not.toContainText("None in this first page.");
  await expect(section(page, "Overdue open tasks")).toContainText("Synthetic overdue inbox task");
  await expect(panel(page)).not.toContainText("Nothing needs attention in the sources that loaded.");
  broken = false;
  const requests: string[] = [];
  page.on("request", r => { const p = new URL(r.url()).pathname; if (READ.has(p)) requests.push(p); });
  await documents.getByRole("button", { name: "Retry documents needing review", exact: true }).click();
  await expect(documents).toContainText("Synthetic inbox unreviewed document");
  expect(requests).toEqual(["/api/v1/documents/query"]);
});

test("task, document, reminder, filing and notification cards open the real related record", async ({ page }) => {
  await login(page);
  const seen = record(page);
  await openInbox(page);
  await refresh(page);
  await expect(panel(page)).toContainText("Inbox loaded.");
  await expect(panel(page)).not.toContainText("does not show this");
  await expect(panel(page)).not.toContainText("(this scope)");
  const back = async () => { await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Attention inbox", exact: true }).click(); await openInbox(page); await refresh(page); await expect(panel(page)).toContainText("Inbox loaded."); };
  await section(page, "Overdue open tasks").getByRole("button", { name: /^Open task: Synthetic overdue inbox task/ }).click();
  await expect(page.getByRole("article", { name: "Selected task", exact: true })).toContainText("Synthetic overdue inbox task");
  await back();
  await section(page, "Documents needing review").getByRole("button", { name: /^Open document: Synthetic inbox unreviewed document/ }).click();
  await expect(page.getByRole("article", { name: "Selected document", exact: true })).toContainText("Synthetic inbox unreviewed document");
  await back();
  // Filing failure: the related document is reread only after the click, under current authorization.
  const beforeFiling = seen.length;
  await expect(section(page, "Failures: filing").getByRole("button", { name: "Open related document", exact: true })).toBeVisible();
  expect(seen.length).toBe(beforeFiling);
  await section(page, "Failures: filing").getByRole("button", { name: "Open related document", exact: true }).click();
  await expect(page.getByRole("article", { name: "Selected document", exact: true })).toContainText("Synthetic inbox filed document");
  await back();
  // Notification failure: the related reminder's task is reread, then the existing reminder read shows it.
  await section(page, "Failures: notifications").getByRole("button", { name: "Open related reminder", exact: true }).click();
  await expect(page.getByRole("article", { name: "Selected private reminder", exact: true })).toContainText("Synthetic inbox delivered reminder");
  await expect(page.getByRole("region", { name: "Private task reminder", exact: true })).toBeVisible();
  const sinceInbox = seen.slice(beforeFiling).map(r => `${r.method} ${r.path}`);
  expect(sinceInbox.some(r => /approvals\/[0-9a-f-]+|\/decide|\/cancel|\/consume|\/retry|\/acknowledge|reminders\/action|reminders\/schedule/.test(r))).toBe(false);
});

