import { expect, test } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";

// Test-process memory only; first sign-in is real HTTPS and each reload rotates CSRF normally.
let cookies: Awaited<ReturnType<BrowserContext["cookies"]>> | null = null;
async function login(page: Page) {
  let csrf: string;
  if (cookies) {
    await page.context().addCookies(cookies);
    const response = page.waitForResponse(r => r.url().endsWith("/api/v1/auth/session") && r.request().method() === "POST");
    await page.goto("/"); csrf = (await (await response).json()).csrf_token;
  } else {
    await page.goto("/"); await page.getByLabel("Username", { exact: true }).fill("browser-capture-flow"); await page.getByLabel("Password", { exact: true }).fill("synthetic-browser-password-only-0123456789");
    const response = page.waitForResponse(r => r.url().endsWith("/api/v1/auth/login") && r.request().method() === "POST"); await page.getByRole("button", { name: "Sign in", exact: true }).click();
    csrf = (await (await response).json()).csrf_token; cookies = await page.context().cookies();
  }
  await expect(page.getByRole("region", { name: "Memory", exact: true })).toBeVisible(); return csrf;
}
async function discovery(page: Page) { await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Discovery", exact: true }).click(); }
async function idea(page: Page, title: string) {
  await discovery(page); await page.getByRole("button", { name: "Add idea", exact: true }).click(); const form = page.getByRole("form", { name: "New Discovery idea", exact: true });
  await form.getByLabel("Idea summary", { exact: true }).fill(title + "\nSynthetic later details"); await expect(form.getByLabel("Idea title", { exact: true })).toHaveValue(title);
  const response = page.waitForResponse(r => r.url().endsWith("/api/v1/discovery/ideas") && r.request().method() === "POST"); await form.getByRole("button", { name: "Save idea", exact: true }).click(); return (await response).json();
}
async function enrich(page: Page) {
  const detail = page.getByRole("article", { name: "Discovery proposal", exact: true }); await detail.getByRole("button", { name: "Add evidence and enrich idea", exact: true }).click(); const form = detail.getByRole("form", { name: "Edit Discovery details", exact: true });
  await form.getByLabel("Proposal topic", { exact: true }).fill("synthetic-capture"); await form.getByLabel("Evidence title", { exact: true }).fill("Synthetic explicit source"); await form.getByLabel("Evidence URL", { exact: true }).fill("https://example.org/synthetic-capture"); await form.getByLabel("Evidence observed at", { exact: true }).fill("2026-01-01T12:00"); return { detail, form };
}

test("minimal Memory capture shows an editable title and explicit tentative provenance, then preserves normal correction", async ({ page }) => {
  await login(page); await page.getByRole("button", { name: "Add memory", exact: true }).click(); const form = page.getByRole("form", { name: "New memory", exact: true });
  await expect(form.getByLabel("Source or reference", { exact: true })).toBeHidden(); await expect(form.getByLabel("Assessment", { exact: true })).toBeHidden();
  await form.getByLabel("Details", { exact: true }).fill("Synthetic quick memory\nAdditional synthetic details"); await expect(form.getByLabel("Title", { exact: true })).toHaveValue("Synthetic quick memory");
  await form.getByLabel("Access", { exact: true }).selectOption("member_a_private"); await expect(form).toContainText("Tentative");
  await page.setViewportSize({ width: 1280, height: 900 }); await form.screenshot({ path: "test-results/memory-quick-capture-desktop.png" }); await page.setViewportSize({ width: 390, height: 844 }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); await form.screenshot({ path: "test-results/memory-quick-capture-mobile.png" });
  const response = page.waitForResponse(r => r.url().endsWith("/api/v1/memory") && r.request().method() === "POST"); await form.getByRole("button", { name: "Save entry", exact: true }).click(); const saved = await (await response).json();
  expect(saved).toMatchObject({ title: "Synthetic quick memory", scope: "member_a_private", assessment: "tentative", source_type: "manual", source_reference: "Manually entered" }); expect(saved.content.text).toContain("Additional synthetic details"); const candidates = await page.evaluate(async () => (await (await fetch("/api/v1/context/candidates?scope=member_a_private")).json()).items); expect(candidates.some((item: { id: string }) => item.id === saved.id)).toBe(false);
  const detail = page.getByRole("article", { name: "Memory details", exact: true }); await detail.getByRole("button", { name: "Edit entry", exact: true }).click();
  const edit = page.getByRole("form", { name: "Edit memory", exact: true }); await edit.getByLabel("Title", { exact: true }).fill("Synthetic reviewed memory"); await edit.getByLabel("Assessment", { exact: true }).selectOption("confirmed"); await edit.getByLabel("Source or reference", { exact: true }).fill("Synthetic explicit reference"); await edit.getByRole("button", { name: "Save entry", exact: true }).click(); await expect(detail).toContainText("Revision 2");
});

test("an evidence-free idea can be enriched and edited without dropping any evidence timestamps", async ({ page }) => {
  test.setTimeout(60000); const csrf = await login(page), row = await idea(page, "Synthetic quick Discovery idea");
  expect(row).toMatchObject({ assessment: "tentative", content: { schema_version: 2, stage: "idea", evidence: [], topic: "unclassified", privacy: "Not assessed" } });
  const { detail, form } = await enrich(page); await form.getByRole("button", { name: "Add evidence row", exact: true }).click(); await form.getByLabel("Evidence 2 title", { exact: true }).fill("Synthetic second source"); await form.getByLabel("Evidence 2 URL", { exact: true }).fill("https://example.org/synthetic-second"); await form.getByLabel("Evidence 2 observed at", { exact: true }).fill("2026-01-02T12:00");
  await page.setViewportSize({ width: 1280, height: 900 }); await form.screenshot({ path: "test-results/discovery-enrich-desktop.png" }); await page.setViewportSize({ width: 390, height: 844 }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); await form.screenshot({ path: "test-results/discovery-enrich-mobile.png" }); await page.setViewportSize({ width: 1280, height: 900 });
  const response = page.waitForResponse(r => r.url().endsWith(`/${row.id}/details`)); await form.getByRole("button", { name: "Save reviewed details", exact: true }).click(); const saved = await (await response).json(); expect(saved.content.stage).toBe("proposal"); expect(saved.content.evidence).toHaveLength(2); await expect(detail).toContainText("Revision 2");
  // Preserve a previously reported offset and fractional second without retyping it in the editor.
  const exact = "2026-01-02T12:00:30.123456+05:30";
  const current = await page.evaluate(async ({ id, csrf, content, exact }) => {
    const { topic, summary, evidence, benefit, privacy, maturity_license, hardware_cost, alternatives_dependencies, experiment } = content;
    evidence[1].observed_at = exact;
    const result = await fetch(`/api/v1/discovery/${id}/details`, { method: "PUT", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ title: "Synthetic precision sources", expected_revision: 2, topic, summary, evidence, benefit, privacy, maturity_license, hardware_cost, alternatives_dependencies, experiment }) }); if (!result.ok) throw new Error("Synthetic enrichment failed"); return result.json();
  }, { id: row.id, csrf, content: saved.content, exact });
  await page.getByRole("button", { name: "Refresh proposals", exact: true }).click(); await page.getByRole("button", { name: /Synthetic precision sources.*Interest score/ }).click(); await detail.getByRole("button", { name: "Edit proposal details", exact: true }).click();
  const editor = detail.getByRole("form", { name: "Edit Discovery details", exact: true }); await editor.getByLabel("Proposal title", { exact: true }).fill("Synthetic evidence preserved"); const corrected = page.waitForResponse(r => r.url().endsWith(`/${row.id}/details`)); await editor.getByRole("button", { name: "Save reviewed details", exact: true }).click(); const after = await (await corrected).json(); expect(after.content.evidence).toEqual(current.content.evidence); expect(after.content.evidence[1].observed_at).toBe(exact);
});

test("details conflict preserves the draft and current feedback until explicit reload", async ({ page }) => {
  const csrf = await login(page), row = await idea(page, "Synthetic conflicting idea"), { detail, form } = await enrich(page);
  await form.getByLabel("Proposal summary", { exact: true }).fill("Synthetic retained details draft");
  const status = await page.evaluate(async ({ id, csrf }) => (await fetch(`/api/v1/discovery/${id}/feedback`, { method: "PUT", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ expected_revision: 1, choice: "later", note: "Synthetic current interest" }) })).status, { id: row.id, csrf }); expect(status).toBe(200);
  await form.getByRole("button", { name: "Save reviewed details", exact: true }).click(); await expect(form).toContainText("draft is kept"); await expect(form.getByLabel("Proposal summary", { exact: true })).toHaveValue("Synthetic retained details draft"); await expect(form.getByRole("button", { name: "Save reviewed details", exact: true })).toBeDisabled();
  await form.getByRole("button", { name: "Discard details draft and reload", exact: true }).click(); await expect(detail).toContainText("Revision 2"); await expect(detail).toContainText("Interest score 10"); await expect(form).toHaveCount(0);
});

test("details denial clears private form state", async ({ page }) => {
  await login(page); await idea(page, "Synthetic denial idea"); const { form } = await enrich(page); await page.route("**/api/v1/discovery/*/details", route => route.fulfill({ status: 403, json: { detail: "Synthetic injected denial" } })); await form.getByRole("button", { name: "Save reviewed details", exact: true }).click(); await expect(form).toHaveCount(0); await expect(page.getByRole("region", { name: "Discovery", exact: true })).not.toContainText("Synthetic denial idea");
});

test("navigation aborts a pending enrichment view and suppresses its late response", async ({ page }) => {
  await login(page); await idea(page, "Synthetic cancelled view"); const { form } = await enrich(page); let release!: () => void, arrived!: () => void; const hold = new Promise<void>(r => { release = r; }), seen = new Promise<void>(r => { arrived = r; });
  await page.route("**/api/v1/discovery/*/details", async route => { const response = await route.fetch(); arrived(); await hold; await route.fulfill({ response }).catch(() => {}); }); await form.getByRole("button", { name: "Save reviewed details", exact: true }).click(); await seen; await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Memory", exact: true }).click(); release(); await expect(form).toHaveCount(0); await page.waitForTimeout(150); await expect(page.getByRole("article", { name: "Discovery proposal", exact: true })).toHaveCount(0);
});

test("temporary Memory still requires an explicit expiry and drafts are discarded on navigation", async ({ page }) => {
  await login(page); await page.getByRole("button", { name: "Add memory", exact: true }).click(); const form = page.getByRole("form", { name: "New memory", exact: true }); await form.getByLabel("Details", { exact: true }).fill("Synthetic temporary context"); await form.getByLabel("Entry type", { exact: true }).selectOption("context"); await expect(form.getByLabel("Expires at (your local time)", { exact: true })).toBeVisible();
  let posts = 0; page.on("request", r => { if (r.url().endsWith("/api/v1/memory") && r.method() === "POST") posts++; }); await form.getByRole("button", { name: "Save entry", exact: true }).click(); expect(posts).toBe(0); await discovery(page); await expect(form).toHaveCount(0); await page.getByRole("button", { name: "Add idea", exact: true }).click(); const ideaForm = page.getByRole("form", { name: "New Discovery idea", exact: true }); await ideaForm.getByLabel("Idea summary", { exact: true }).fill("Synthetic unsaved idea"); await ideaForm.getByRole("button", { name: "Cancel idea", exact: true }).click(); await expect(ideaForm).toHaveCount(0);
});
