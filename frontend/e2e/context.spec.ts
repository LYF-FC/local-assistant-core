import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function login(page: Page, slug: string) {
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(slug);
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password-only-0123456789');
  const response = page.waitForResponse(r => r.url().endsWith('/api/v1/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const data = await (await response).json();
  await expect(page.getByRole('region', { name: 'Memory', exact: true })).toBeVisible();
  return data.csrf_token as string;
}
async function create(page: Page, csrf: string, title: string, changes: Record<string, unknown> = {}) {
  return page.evaluate(async ({ csrf, title, changes }) => {
    const response = await fetch('/api/v1/memory', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ scope: 'member_a_private', kind: 'preference', title, content: { text: 'Synthetic preview source' }, source_type: 'manual', source_reference: 'Synthetic preview provenance', assessment: 'confirmed', expires_at: null, ...changes }) });
    if (response.status !== 201) throw new Error('Synthetic source creation failed');
    return response.json();
  }, { csrf, title, changes });
}
async function openContext(page: Page) {
  await page.getByRole('navigation', { name: 'Local records' }).getByRole('button', { name: 'Context preview', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Context preview', exact: true })).toBeVisible();
}
test('explicit eligible preview, safe provenance and all-or-nothing byte budget', async ({ page }) => {
  const csrf = await login(page, 'browser-context-owner');
  await create(page, csrf, 'Synthetic preview preference', { content: { text: '<img src=x onerror="window.contextInjected=true">Synthetic safe reference' } });
  await create(page, csrf, 'Synthetic preview procedure', { kind: 'procedure', content: { steps: ['Synthetic first step', 'Synthetic second step'] } });
  await create(page, csrf, 'Synthetic tentative exclusion', { assessment: 'tentative' });
  await create(page, csrf, 'Synthetic experience exclusion', { kind: 'experience' });
  await create(page, csrf, 'Synthetic large reference', { content: { text: 'x'.repeat(5000) } });
  let catalogueRequests = 0; page.on('request', r => { if (r.url().includes('/api/v1/context/candidates')) catalogueRequests += 1; });
  await openContext(page);
  await expect(page.getByText('Choose an assigned scope to load eligible records.')).toBeVisible();
  expect(catalogueRequests).toBe(0);
  await page.getByLabel('Context scope', { exact: true }).selectOption('member_a_private');
  await expect(page.getByLabel('Select Synthetic preview preference', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Select Synthetic tentative exclusion', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Select Synthetic experience exclusion', { exact: true })).toHaveCount(0);
  await page.getByLabel('Select Synthetic preview preference', { exact: true }).check();
  await page.getByLabel('Select Synthetic preview procedure', { exact: true }).check();
  await page.getByRole('button', { name: 'Build preview', exact: true }).click();
  const preview = page.getByRole('region', { name: 'Built context preview', exact: true });
  await expect(preview).toContainText('Synthetic safe reference');
  await expect(preview).toContainText('Synthetic second step');
  await expect(preview).toContainText('Synthetic preview provenance');
  await expect(preview.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => 'contextInjected' in window)).toBe(false);
  await page.screenshot({ path: 'test-results/context-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/context-mobile.png', fullPage: true }); await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByLabel('Items byte budget', { exact: true }).selectOption('2048');
  await expect(preview).toHaveCount(0);
  await page.getByRole('button', { name: 'Clear selection and preview', exact: true }).click();
  await page.getByLabel('Select Synthetic large reference', { exact: true }).check();
  await page.getByRole('button', { name: 'Build preview', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('exceeds the byte budget');
  await expect(preview).toHaveCount(0);
  await expect(page.getByLabel('Select Synthetic large reference', { exact: true })).toBeChecked();
});
test('stale selection clears and a refreshed short-lived preview expires', async ({ page }) => {
  const csrf = await login(page, 'browser-context-conflict');
  const record = await create(page, csrf, 'Synthetic changing reference'); await openContext(page);
  await page.getByLabel('Context scope', { exact: true }).selectOption('member_a_private');
  await page.getByLabel('Select Synthetic changing reference', { exact: true }).check();
  const status = await page.evaluate(async ({ csrf, record }) => (await fetch(`/api/v1/memory/${record.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ expected_revision: 1, title: record.title, content: { text: 'Synthetic newly corrected reference' }, source_type: record.source_type, source_reference: record.source_reference, assessment: record.assessment, expires_at: record.expires_at }) })).status, { csrf, record });
  expect(status).toBe(200);
  await page.getByRole('button', { name: 'Build preview', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Selected records changed');
  await expect(page.getByLabel('Select Synthetic changing reference', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Refresh candidates', exact: true }).click();
  await page.getByLabel('Select Synthetic changing reference', { exact: true }).check();
  // Shorten this synthetic response's lifetime to test UI expiry without a 60s wait.
  await page.route('**/api/v1/context/preview', async route => {
    const response = await route.fetch(); const data = await response.json();
    if (response.status() === 200) { data.generated_at = new Date().toISOString(); data.valid_until = new Date(Date.now() + 2000).toISOString(); }
    await route.fulfill({ response, json: data });
  });
  await page.getByRole('button', { name: 'Build preview', exact: true }).click();
  const preview = page.getByRole('region', { name: 'Built context preview', exact: true });
  await expect(preview).toContainText('Synthetic newly corrected reference');
  await expect(page.getByText('Preview expired and cleared. Build again to recheck current records.')).toBeVisible();
  await expect(preview).toHaveCount(0);
});
test('sign-out cancels a delayed preview across users', async ({ page }) => {
  const csrf = await login(page, 'browser-context-race');
  await create(page, csrf, 'Synthetic private preview race'); await openContext(page);
  await page.getByLabel('Context scope', { exact: true }).selectOption('member_a_private');
  await page.getByLabel('Select Synthetic private preview race', { exact: true }).check();
  let release!: () => void; let held = false; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/context/preview', async route => {
    const response = await route.fetch(); const data = await response.json(); held = true; await gate;
    try { await route.fulfill({ status: response.status(), contentType: 'application/json', body: JSON.stringify(data) }); } catch { /* Aborted by session unmount. */ }
  });
  await page.getByRole('button', { name: 'Build preview', exact: true }).click(); await expect.poll(() => held).toBe(true);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('form', { name: 'Sign in' })).toBeVisible(); release();
  await login(page, 'browser-memory-viewer'); await openContext(page);
  await page.getByLabel('Context scope', { exact: true }).selectOption('member_a_private');
  await expect(page.getByText('No eligible records in this scope. Use Memory to inspect other entries.')).toBeVisible();
  await expect(page.getByText('Synthetic private preview race', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Built context preview', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
});
test('scope change cancels an older catalogue and denial clears current choices', async ({ page }) => {
  const csrf = await login(page, 'browser-context-scope');
  await create(page, csrf, 'Synthetic delayed catalogue marker');
  await create(page, csrf, 'Synthetic shared catalogue marker', { scope: 'household_shared' }); await openContext(page);
  let release!: () => void; let held = false; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/context/candidates?*', async route => {
    if (!route.request().url().includes('scope=member_a_private')) { await route.continue(); return; }
    const response = await route.fetch(); const data = await response.json(); held = true; await gate;
    try { await route.fulfill({ status: response.status(), contentType: 'application/json', body: JSON.stringify(data) }); } catch { /* Aborted by scope change. */ }
  });
  await page.getByLabel('Context scope', { exact: true }).selectOption('member_a_private'); await expect.poll(() => held).toBe(true);
  await page.getByLabel('Context scope', { exact: true }).selectOption('household_shared');
  await expect(page.getByLabel('Select Synthetic shared catalogue marker', { exact: true })).toBeVisible(); release();
  await expect(page.getByLabel('Select Synthetic delayed catalogue marker', { exact: true })).toHaveCount(0);
  await page.route('**/api/v1/context/preview', route => route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Access denied"}' }));
  await page.getByLabel('Select Synthetic shared catalogue marker', { exact: true }).check();
  await page.getByRole('button', { name: 'Build preview', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Context is no longer available');
  await expect(page.getByLabel('Select Synthetic shared catalogue marker', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Refresh candidates', exact: true })).toBeEnabled();
});
