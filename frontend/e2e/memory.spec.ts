import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";

async function login(page: Page, slug: string): Promise<string> {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(slug);
  await page.getByLabel("Password", { exact: true }).fill("synthetic-browser-password-only-0123456789");
  const loginResponse = page.waitForResponse(response => response.url().endsWith("/api/v1/auth/login") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const data = await (await loginResponse).json();
  await expect(page.getByRole("region", { name: "Memory", exact: true })).toBeVisible();
  return data.csrf_token;
}
test("owner creates, corrects, inspects history, exports and forgets safely", async ({ page }) => {
  await login(page, "browser-memory-owner");
  await expect(page.getByRole("button", { name: /Expired synthetic context/ })).toHaveCount(0);
  await page.getByLabel("Include my expired entries").check();
  await page.getByRole("button", { name: /Expired synthetic context/ }).click();
  await expect(page.getByRole("article", { name: "Memory details" })).toContainText("excluded from current context");
  await page.getByLabel("Include my expired entries").uncheck();
  await page.getByLabel("Filter access").selectOption("member_a_private");
  await page.getByLabel("Filter type").selectOption("preference");
  await page.getByRole("button", { name: "Add memory", exact: true }).click();
  const form = page.getByRole("form", { name: "New memory" });
  await form.getByLabel("Title", { exact: true }).fill("Synthetic UI preference");
  await form.getByLabel("Details", { exact: true }).fill('<img src=x onerror="window.memoryInjected=true">Synthetic UI details');
  await form.getByLabel("Access", { exact: true }).selectOption("member_a_private");
  await form.getByText("Source, assessment and optional details", { exact: true }).click();
  await form.getByLabel("Source or reference").fill("Synthetic original source");
  const created = page.waitForResponse(response => response.url().endsWith("/api/v1/memory") && response.request().method() === "POST");
  await form.getByRole("button", { name: "Save entry" }).click();
  const record = await (await created).json();
  const detail = page.getByRole("article", { name: "Memory details" });
  await expect(detail).toContainText("Synthetic UI details");
  await expect(detail.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => "memoryInjected" in window)).toBe(false);
  await detail.getByRole("button", { name: "Edit entry" }).click();
  const editor = page.getByRole("form", { name: "Edit memory" });
  await expect(editor).toBeVisible();
  await page.screenshot({ path: "test-results/memory-editor.png", fullPage: true });
  await editor.getByLabel("Details", { exact: true }).fill("Corrected synthetic details");
  await editor.getByLabel("Source or reference").fill("Synthetic corrected source");
  await editor.getByRole("button", { name: "Save entry" }).click();
  await expect(detail).toContainText("Revision 2");
  await detail.getByRole("button", { name: "View history" }).click();
  const history = page.getByRole("region", { name: "Memory history" });
  await expect(history).toContainText("Synthetic original source");
  await expect(history).toContainText("Corrected synthetic details");
  await page.screenshot({ path: "test-results/memory-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/memory-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download this page" }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("butler-memory-page.json");
  const exported = JSON.parse(readFileSync((await download.path())!, "utf8"));
  expect(exported.schema_version).toBe(1);
  expect(exported.items.find((item: { id: string }) => item.id === record.id).content.text).toBe("Corrected synthetic details");
  await detail.getByRole("button", { name: "Forget entry" }).click();
  const dialog = page.getByRole("dialog", { name: "Forget this memory?" });
  await expect(dialog).toContainText("older backups can retain copies");
  await dialog.getByRole("button", { name: "Keep entry" }).click();
  await expect(detail).toContainText("Corrected synthetic details");
  // Hold a list response from before forgetting; it must not restore the record.
  await detail.getByRole("button", { name: "Edit entry" }).click();
  let releaseOldList!: () => void; let oldListHeld = false; let beforeForget: unknown;
  const oldListGate = new Promise<void>(resolve => { releaseOldList = resolve; });
  await page.route('**/api/v1/memory?*', async route => {
    if (oldListHeld) { await route.continue(); return; }
    oldListHeld = true; await oldListGate;
    try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 1, generated_at: new Date().toISOString(), items: [beforeForget], next_cursor: null }) }); } catch { /* Confirmed forgetting aborts older payload. */ }
  });
  const correctedAgain = page.waitForResponse(response => response.url().includes(record.id) && response.request().method() === 'PATCH');
  await page.getByRole("form", { name: "Edit memory" }).getByRole("button", { name: "Save entry" }).click();
  beforeForget = await (await correctedAgain).json();
  await expect.poll(() => oldListHeld).toBe(true);
  await detail.getByRole("button", { name: "Forget entry" }).click();
  await dialog.getByRole("button", { name: "Forget permanently from live memory" }).click();
  releaseOldList();
  await expect(page.getByText("Memory forgotten from live records and saved revisions.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Memory history" })).toHaveCount(0);
  await expect(page.getByRole("article", { name: "Memory details" })).toHaveCount(0);
  const snapshots = await page.evaluate(async id => (await (await fetch(`/api/v1/memory/${id}/history`)).json()).items, record.id);
  expect(snapshots.every((item: { snapshot: unknown }) => item.snapshot === null)).toBe(true);
});
test("structured details survive correction and stale edits require explicit reload", async ({ page }) => {
  const csrf = await login(page, "browser-memory-conflict");
  await page.getByRole("button", { name: /Structured synthetic memory/ }).click();
  const detail = page.getByRole("article", { name: "Memory details" });
  await detail.getByRole("button", { name: "Edit entry" }).click();
  let editor = page.getByRole("form", { name: "Edit memory" });
  await expect(editor).toContainText("will be preserved");
  await editor.getByLabel("Title", { exact: true }).fill("Structured synthetic corrected");
  await editor.getByRole("button", { name: "Save entry" }).click();
  await expect(detail).toContainText("Revision 2");
  await detail.getByRole("button", { name: "Edit entry" }).click();
  editor = page.getByRole("form", { name: "Edit memory" });
  await editor.getByLabel("Title", { exact: true }).fill("Unsaved synthetic draft");
  const result = await page.evaluate(async csrfToken => {
    const id = "83333333-3333-4333-8333-333333333333";
    const before = await (await fetch(`/api/v1/memory/${id}`)).json();
    const response = await fetch(`/api/v1/memory/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken }, body: JSON.stringify({ expected_revision: before.revision, title: "External synthetic correction", content: before.content, source_type: before.source_type, source_reference: before.source_reference, assessment: before.assessment, expires_at: before.expires_at }) });
    return { status: response.status, content: before.content };
  }, csrf);
  expect(result.status).toBe(200);
  expect(result.content).toEqual({ camera: "synthetic-camera", tags: ["one", "two"] });
  await editor.getByRole("button", { name: "Save entry" }).click();
  await expect(page.getByRole("alert")).toContainText("This entry changed");
  await expect(editor.getByLabel("Title", { exact: true })).toHaveValue("Unsaved synthetic draft");
  await expect(editor.getByRole("button", { name: "Save entry" })).toBeDisabled();
  await editor.getByRole("button", { name: "Discard draft and reload" }).click();
  await expect(detail).toContainText("External synthetic correction");
  await expect(detail).toContainText("Revision 3");
});
test("private ownership and shared controls hold; late export cannot survive sign-out", async ({ page }) => {
  await login(page, "browser-memory-viewer");
  await expect(page.getByRole("button", { name: /Shared synthetic marker/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Private synthetic marker/ })).toHaveCount(0);
  await page.getByRole("button", { name: /Shared synthetic marker/ }).click();
  const detail = page.getByRole("article", { name: "Memory details" });
  await expect(detail.getByRole("button", { name: "Edit entry" })).toHaveCount(0);
  await expect(detail.getByRole("button", { name: "View history" })).toHaveCount(0);
  await expect(detail.getByRole("button", { name: "Forget entry" })).toHaveCount(0);
  const denied = await page.evaluate(async () => ({ private: (await fetch('/api/v1/memory/81111111-1111-4111-8111-111111111111')).status, history: (await fetch('/api/v1/memory/82222222-2222-4222-8222-222222222222/history')).status }));
  expect(denied).toEqual({ private: 404, history: 403 });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await login(page, "browser-memory-race");
  await expect(page.getByRole("button", { name: /Race synthetic marker/ })).toBeVisible();
  let release!: () => void;
  let held = false;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let downloads = 0; page.on("download", () => { downloads += 1; });
  await page.route('**/api/v1/memory/export?*', async route => {
    held = true; await gate;
    try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 1, generated_at: new Date().toISOString(), items: [], next_cursor: null }) }); } catch { /* Request was correctly aborted by sign-out. */ }
  });
  await page.getByRole("button", { name: "Download this page" }).click();
  await expect.poll(() => held).toBe(true);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("form", { name: "Sign in" })).toBeVisible();
  release();
  await login(page, "browser-memory-viewer");
  await expect(page.getByRole("button", { name: /Shared synthetic marker/ })).toBeVisible();
  await expect(page.getByText("Race synthetic marker", { exact: true })).toHaveCount(0);
  expect(downloads).toBe(0);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
});

test("access denial clears cached details and aborts an older list response", async ({ page }) => {
  await login(page, "browser-memory-denial");
  await page.getByRole("button", { name: /Denial synthetic marker/ }).click();
  const detail = page.getByRole("article", { name: "Memory details" });
  await detail.getByRole("button", { name: "Edit entry" }).click();
  await page.getByRole("form", { name: "Edit memory" }).getByLabel("Title", { exact: true }).fill("Denial synthetic corrected");
  let release!: () => void; let held = false;
  let entry: unknown;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/memory?*', async route => {
    held = true; await gate;
    try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 1, generated_at: new Date().toISOString(), items: [entry], next_cursor: null }) }); } catch { /* The denial must abort this older request. */ }
  });
  const corrected = page.waitForResponse(response => response.url().includes('/api/v1/memory/86666666') && response.request().method() === 'PATCH');
  await page.getByRole("form", { name: "Edit memory" }).getByRole("button", { name: "Save entry" }).click();
  entry = await (await corrected).json();
  await expect(detail).toContainText("Denial synthetic corrected");
  await expect.poll(() => held).toBe(true);
  await page.route('**/api/v1/memory/86666666-6666-4666-8666-666666666666/history?*', route => route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Access denied"}' }));
  await detail.getByRole("button", { name: "View history" }).click();
  await expect(page.getByRole("alert")).toContainText("no longer available");
  release();
  await expect(page.getByRole("article", { name: "Memory details" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Denial synthetic corrected/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Refresh list", exact: true })).toBeEnabled();
});
