import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function login(page: Page, slug: string) {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(slug);
  await page.getByLabel("Password", { exact: true }).fill("synthetic-browser-password-only-0123456789");
  const response = page.waitForResponse(r => r.url().endsWith("/api/v1/auth/login") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const data = await (await response).json();
  await expect(page.getByRole("region", { name: "Memory", exact: true })).toBeVisible();
  return data.csrf_token as string;
}
async function openDiscovery(page: Page) {
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Discovery", exact: true }).click();
  await expect(page.getByRole("region", { name: "Discovery", exact: true })).toBeVisible();
}
async function seed(page: Page, csrf: string, title: string) {
  return page.evaluate(async ({ csrf, title }) => {
    const result = await fetch('/api/v1/discovery', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ scope: 'member_a_private', title, topic: 'synthetic-discovery', summary: 'Synthetic summary', evidence: [{ title: 'Synthetic source', url: 'https://example.org/source', observed_at: '2026-01-01T00:00:00Z' }] }) });
    if (result.status !== 201) throw new Error('Synthetic creation failed');
    return result.json();
  }, { csrf, title });
}
test("manual proposal feedback, clearing, dismissal and memory forgetting", async ({ page }) => {
  await login(page, 'browser-discovery-flow'); await openDiscovery(page);
  await page.getByRole('button', { name: 'Add proposal', exact: true }).click();
  const form = page.getByRole('form', { name: 'New Discovery proposal' });
  await form.getByLabel('Proposal title', { exact: true }).fill('Synthetic Discovery proposal');
  await form.getByLabel('Proposal topic', { exact: true }).fill('synthetic-tagging');
  await form.getByLabel('Proposal summary', { exact: true }).fill('<img src=x onerror="window.discoveryInjected=true">Synthetic research');
  await form.getByLabel('Evidence title', { exact: true }).fill('Synthetic primary evidence');
  await form.getByLabel('Evidence URL', { exact: true }).fill('https://example.org/synthetic');
  await form.getByLabel('Evidence observed at', { exact: true }).fill('2026-01-01T12:00');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/discovery-editor.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/discovery') && r.request().method() === 'POST');
  await form.getByRole('button', { name: 'Save proposal' }).click();
  const record = await (await created).json();
  const detail = page.getByRole('article', { name: 'Discovery proposal', exact: true });
  await expect(detail).toContainText('Not assessed');
  await expect(detail.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => 'discoveryInjected' in window)).toBe(false);
  await detail.getByLabel('Your interest', { exact: true }).selectOption('very_interested');
  await detail.getByLabel('Feedback note', { exact: true }).fill('Synthetic explicit preference');
  await detail.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await expect(detail).toContainText('Revision 2'); await expect(detail).toContainText('Interest score 100');
  await page.screenshot({ path: 'test-results/discovery-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/discovery-mobile.png', fullPage: true }); await page.setViewportSize({ width: 1280, height: 720 });
  await detail.getByRole('button', { name: 'Clear feedback', exact: true }).click();
  await expect(detail).toContainText('Revision 3'); await expect(detail).toContainText('Interest score 0');
  await detail.getByLabel('Your interest', { exact: true }).selectOption('not_relevant');
  await detail.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await expect(detail).toContainText('Revision 4');
  await expect(page.getByRole('button', { name: /Synthetic Discovery proposal.*Interest score/ })).toHaveCount(0);
  await page.getByLabel('Include dismissed proposals').check();
  await page.getByRole('button', { name: /Synthetic Discovery proposal.*Interest score/ }).click();
  await expect(detail).toContainText('Interest score -20');
  await page.getByRole('navigation', { name: 'Local records' }).getByRole('button', { name: 'Memory', exact: true }).click();
  await page.getByRole('button', { name: /Synthetic Discovery proposal.*Experience/ }).click();
  const memory = page.getByRole('article', { name: 'Memory details', exact: true });
  await memory.getByRole('button', { name: 'View history' }).click();
  await expect(page.getByRole('region', { name: 'Memory history' })).toContainText('Synthetic explicit preference');
  await memory.getByRole('button', { name: 'Forget entry' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Forget permanently from live memory' }).click();
  await expect(page.getByText('Memory forgotten from live records and saved revisions.')).toBeVisible();
  await openDiscovery(page);
  await expect(page.getByText('No proposals match this view.')).toBeVisible();
  const history = await page.evaluate(async id => (await (await fetch(`/api/v1/memory/${id}/history`)).json()).items, record.id);
  expect(history.every((row: { snapshot: unknown }) => row.snapshot === null)).toBe(true);
});
test("feedback conflict preserves draft until explicit discard", async ({ page }) => {
  const csrf = await login(page, 'browser-discovery-conflict');
  const record = await seed(page, csrf, 'Synthetic concurrent proposal'); await openDiscovery(page);
  await page.getByRole('button', { name: /Synthetic concurrent proposal.*Interest score/ }).click();
  const detail = page.getByRole('article', { name: 'Discovery proposal', exact: true });
  await detail.getByLabel('Your interest', { exact: true }).selectOption('very_interested');
  await detail.getByLabel('Feedback note', { exact: true }).fill('Synthetic retained draft');
  const status = await page.evaluate(async ({ csrf, id }) => (await fetch(`/api/v1/discovery/${id}/feedback`, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ expected_revision: 1, choice: 'later', note: 'Other synthetic correction' }) })).status, { csrf, id: record.id });
  expect(status).toBe(200);
  await detail.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Your feedback draft is kept');
  await expect(detail.getByLabel('Feedback note', { exact: true })).toHaveValue('Synthetic retained draft');
  await expect(detail.getByRole('button', { name: 'Save feedback', exact: true })).toBeDisabled();
  await detail.getByRole('button', { name: 'Discard feedback draft and reload' }).click();
  await expect(detail).toContainText('Revision 2');
  await expect(detail.getByLabel('Feedback note', { exact: true })).toHaveValue('Other synthetic correction');
});
test("sign-out aborts a delayed proposal list across users", async ({ page }) => {
  const csrf = await login(page, 'browser-discovery-race');
  const record = await seed(page, csrf, 'Synthetic private delayed proposal');
  let release!: () => void; let held = false;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/discovery/inbox', async route => {
    if (held) { await route.continue(); return; }
    held = true; await gate;
    try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 1, items: [record], next_cursor: null }) }); } catch { /* Aborted on sign-out. */ }
  });
  await openDiscovery(page); await expect.poll(() => held).toBe(true);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('form', { name: 'Sign in' })).toBeVisible(); release();
  await login(page, 'browser-memory-viewer'); await openDiscovery(page);
  await expect(page.getByText('No proposals match this view.')).toBeVisible();
  await expect(page.getByText('Synthetic private delayed proposal', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
});
