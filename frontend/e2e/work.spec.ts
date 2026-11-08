import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
async function openWork(page: Page, slug: string) {
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(slug);
  await page.getByLabel('Password', { exact: true }).fill('synthetic-browser-password-only-0123456789');
  const loginResponse = page.waitForResponse(r => r.url().endsWith('/api/v1/auth/login') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const auth = await (await loginResponse).json();
  await page.getByRole('navigation', { name: 'Local records' }).getByRole('button', { name: 'Work Companion', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Work Companion', exact: true })).toBeVisible();
  return auth.csrf_token as string;
}
test('explicit workspace load, disabled status, denial clears and family admin has no implicit grant', async ({ page }) => {
  let reads = 0; page.on('request', request => { if (request.url().includes('/api/v1/work/')) reads += 1; });
  await openWork(page, 'browser-work-owner');
  expect(reads).toBe(0);
  await page.getByRole('button', { name: 'Load assigned workspaces', exact: true }).click();
  await page.getByRole('button', { name: 'synthetic-browser-work', exact: true }).click();
  const selected = page.getByRole('region', { name: 'Selected work access', exact: true });
  await expect(selected).toContainText('Ingestion remains disabled');
  await expect(selected).toContainText('Dedicated work content storage');
  await expect(selected.locator('time')).toHaveAttribute('datetime', /T/);
  await expect(selected.getByRole('button', { name: 'Recheck current access', exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/work-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/work-mobile.png", fullPage: true });
  await page.route('**/api/v1/work/workspaces/*/status', route => route.fulfill({ status: 404, json: { detail: 'Access denied' } }));
  await selected.getByRole('button', { name: 'Recheck current access', exact: true }).click();
  await expect(selected).toHaveCount(0);
  await expect(page.getByRole('alert')).toContainText('Workspace access is unavailable');
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await openWork(page, 'browser-work-viewer');
  await page.getByRole('button', { name: 'Load assigned workspaces', exact: true }).click();
  await expect(page.getByText('No active workspaces are assigned to your account.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'synthetic-browser-work', exact: true })).toHaveCount(0);
});
test('delayed status cannot restore a signed-out work view', async ({ page }) => {
  await openWork(page, 'browser-work-race');
  await page.getByRole('button', { name: 'Load assigned workspaces', exact: true }).click();
  let release!: () => void; const hold = new Promise<void>(resolve => { release = resolve; });
  let reached!: () => void; const started = new Promise<void>(resolve => { reached = resolve; });
  await page.route('**/api/v1/work/workspaces/*/status', async route => {
    const response = await route.fetch(); reached(); await hold;
    try { await route.fulfill({ response }); } catch { /* UI aborted on unmount */ }
  });
  await page.getByRole('button', { name: 'synthetic-browser-race', exact: true }).click();
  await started;
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  release();
  await expect(page.getByRole('form', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Selected work access', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Work Companion', exact: true })).toHaveCount(0);
});


test('synthetic storage read stays disabled and requires CSRF over real TLS', async ({ page }) => {
  const csrf = await openWork(page, 'browser-work-owner');
  const result = await page.evaluate(async csrf => {
    const list = await (await fetch('/api/v1/work/workspaces')).json();
    const id = list.items.find((w: { slug: string }) => w.slug === 'synthetic-browser-work').id;
    const send = async (token: string) => {
      const response = await fetch(`/api/v1/work/workspaces/${id}/validation-read`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token }, body: '{}' });
      return { status: response.status, body: await response.json() };
    };
    const draft = `/api/v1/work/workspaces/${id}/drafts/11111111-1111-4111-8111-111111111111`;
    const preview = await fetch(draft+'/preview', { method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:'{}' });
    const review = await fetch(draft+'/review', { method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify({expected_revision:1, reviewed_hash:'0'.repeat(64), request_id:crypto.randomUUID(), decision:'approve'}) });
    return { disabled: await send(csrf), denied: await send('invalid-csrf'), previewStatus:preview.status, reviewStatus:review.status };
  }, csrf);
  expect(result.disabled.status).toBe(503);
  expect(result.disabled.body).toEqual({ detail: 'Work validation unavailable' });
  expect(result.denied.status).toBe(403);
  expect(result.previewStatus).toBe(503);
  expect(result.reviewStatus).toBe(503);
  expect(result.disabled.body).not.toHaveProperty('items');
});
