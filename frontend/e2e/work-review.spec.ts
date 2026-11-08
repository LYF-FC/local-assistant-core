import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { openSyntheticSession } from "./work-browser-session";

test.skip(process.env.BUTLER_WORK_NOTES_BROWSER_TESTS !== "1", "Optional synthetic interface overlay required");
test.use({ timezoneId: "UTC" });
const ack = "I reviewed the visible report and will manage its copy and retention";
const names = ["meeting-action-owned", "meeting-action-unknown", "meeting-decision", "meeting-question", "meeting-observation"];
async function open(page: Page) {
  await openSyntheticSession(page, "browser-work-meeting");
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Work Companion", exact: true }).click();
  await page.getByRole("button", { name: "Load assigned workspaces", exact: true }).click();
  await page.getByRole("button", { name: "synthetic-adapter-ci", exact: true }).click();
  const notes = page.getByRole("region", { name: "Synthetic Work notes", exact: true });
  await notes.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  await notes.getByRole("button", { name: "Review work and prepare a report", exact: true }).click();
  const panel = page.getByRole("region", { name: "Sample work review workspace", exact: true });
  for (const name of names) await panel.getByRole("checkbox", { name: `Review note ${name}`, exact: true }).check();
  const response = page.waitForResponse(r => r.url().endsWith("/notes/export") && r.request().postDataJSON().purpose === "preview");
  await panel.getByRole("button", { name: "Load selected work review", exact: true }).click();
  const reviewed = await (await response).json();
  await expect(panel.getByRole("region", { name: "Reviewed work snapshot", exact: true })).toBeVisible();
  return { panel, reviewed, notes };
}

test("real selected review intersects facets and downloads the visible cited report from a fresh hash-bound export", async ({ page }) => {
  test.setTimeout(60000); await page.clock.install();
  const errors: string[] = []; page.on("pageerror", e => errors.push(e.message)); page.on("console", m => { if (m.type() === "error" && /same key|unique.*key/i.test(m.text())) errors.push(m.text()); });
  const { panel, reviewed, notes } = await open(page);
  const calls: Record<string, unknown>[] = []; page.on("request", r => { if (r.url().endsWith("/notes/export")) calls.push(r.postDataJSON()); });
  await expect(panel.getByRole("checkbox", { name: "Review note export-draft", exact: true })).toHaveCount(0);
  const summary = panel.getByRole("region", { name: "Visible review summary", exact: true });
  await expect(summary).toContainText("5 visible of 5 selected notes");
  await expect(summary).toContainText("Confirmation is not completion");
  await panel.getByLabel("Action due date", { exact: true }).selectOption("next7");
  await expect(summary).toContainText("1 visible of 5 selected notes");
  await expect(panel.getByRole("region", { name: "Visible reviewed notes", exact: true })).toContainText("meeting-action-owned");
  await panel.getByLabel("Action due date", { exact: true }).selectOption("unknown");
  await expect(panel.getByRole("region", { name: "Visible reviewed notes", exact: true })).toContainText("meeting-action-unknown");
  await panel.getByLabel("Action due date", { exact: true }).selectOption("all");
  const owned = reviewed.bundle.items.find((n: { item: { owner_id: string | null } }) => n.item.owner_id !== null);
  await panel.getByLabel("Note owner", { exact: true }).selectOption(owned.item.owner_id); await expect(summary).toContainText("1 visible of 5 selected notes");
  await panel.getByLabel("Note owner", { exact: true }).selectOption("all");
  await panel.getByLabel("Source reference", { exact: true }).selectOption(reviewed.bundle.items[0].item.source_ids[0]);
  await panel.getByLabel("Activity view", { exact: true }).selectOption("updated"); await expect(summary).toContainText("5 visible of 5 selected notes");
  await panel.getByLabel("Note kind", { exact: true }).selectOption("decision");
  await panel.getByLabel("Search selected notes", { exact: true }).fill("meeting-decision");
  await panel.getByLabel("Report title", { exact: true }).fill("Sample weekly CTO status");
  await panel.getByLabel("Review order", { exact: true }).selectOption("updated");
  await expect(summary).toContainText("1 visible of 5 selected notes");
  const decision = reviewed.bundle.items.find((n: { item: { kind: string } }) => n.item.kind === "decision");
  await panel.getByText("Sources and record version for meeting-decision", { exact: true }).click(); await expect(panel).toContainText(decision.item.id);
  await panel.getByText("Sources and record version for meeting-decision", { exact: true }).click();
  await expect(panel.getByRole("button", { name: "Download reviewed work report", exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 1280, height: 900 }); await panel.screenshot({ path: "test-results/work-review-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); await panel.screenshot({ path: "test-results/work-review-mobile.png" });
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  const downloaded = page.waitForEvent("download"), response = page.waitForResponse(r => r.url().endsWith("/notes/export") && r.request().postDataJSON().purpose === "download");
  await panel.getByRole("button", { name: "Download reviewed work report", exact: true }).click();
  const file = await downloaded, fresh = await (await response).json(), text = readFileSync((await file.path())!, "utf8");
  expect(fresh.bundle.export_id).not.toBe(reviewed.bundle.export_id); expect(text).toContain(`Export reference: \`${fresh.bundle.export_id}\``); expect(text).not.toContain(reviewed.bundle.export_id);
  expect(text).toContain("Title: Sample weekly CTO status"); expect(text).toContain("Coverage: 1 visible of 5"); expect(text).toContain(`Note \`${decision.item.id}\`, version ${decision.item.revision}`);
  expect(text).not.toContain(owned.item.id); expect(text).toContain("not event history"); expect(text).toContain("Completion is Unknown");
  expect(file.suggestedFilename()).toBe(`butler-work-report-${fresh.bundle.workspace_id}-${fresh.bundle.export_id}.md`);
  expect(calls).toHaveLength(1); expect(calls[0]).toMatchObject({ include_drafts: false, purpose: "download", acknowledge_copy_limits: true, reviewed_hash: reviewed.reviewed_hash }); expect((calls[0].selections as unknown[])).toHaveLength(5);
  expect(JSON.stringify(calls)).not.toContain("Sample weekly CTO status"); expect(JSON.stringify(calls)).not.toContain("meeting-decision");
  await expect(panel).toHaveCount(0); await expect(notes).toContainText("A work status report download was requested"); expect(errors).toEqual([]);
});

test("filter and annotation edits revoke acknowledgement; empty or invalid windows cannot download", async ({ page }) => {
  await page.clock.install(); const { panel } = await open(page), check = panel.getByRole("checkbox", { name: ack, exact: true });
  await check.check(); await panel.getByLabel("Search selected notes", { exact: true }).fill("no matching sample");
  await expect(check).not.toBeChecked(); await expect(check).toBeDisabled(); await expect(panel.getByRole("button", { name: "Download reviewed work report", exact: true })).toBeDisabled();
  await panel.getByRole("button", { name: "Reset review filters", exact: true }).click(); await check.check();
  await panel.getByLabel("Report title", { exact: true }).fill("Changed sample report"); await expect(check).not.toBeChecked();
  await panel.getByLabel("Activity window start (UTC)", { exact: true }).fill("2030-01-01T00:00"); await expect(panel.getByRole("alert")).toContainText("366 days"); await expect(panel.getByRole("button", { name: "Download reviewed work report", exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: "Reset review filters", exact: true }).click(); await expect(check).not.toBeChecked();
});

test("selection and sibling tools invalidate private snapshots and never reuse acknowledgements", async ({ page }) => {
  await page.clock.install(); const { panel, notes } = await open(page);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check(); await panel.getByRole("checkbox", { name: "Review note meeting-question", exact: true }).uncheck();
  await expect(panel.getByRole("region", { name: "Reviewed work snapshot", exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: "Load selected work review", exact: true }).click(); await expect(panel.getByRole("checkbox", { name: ack, exact: true })).not.toBeChecked();
  await notes.getByRole("button", { name: "Prepare a meeting", exact: true }).click(); await expect(panel).toHaveCount(0);
  await notes.getByRole("button", { name: "Review work and prepare a report", exact: true }).click(); await expect(notes.getByRole("region", { name: "Sample meeting workbench", exact: true })).toHaveCount(0);
  await notes.getByRole("button", { name: "Export selected notes", exact: true }).click(); await expect(panel).toHaveCount(0);
  await notes.getByRole("button", { name: "Review work and prepare a report", exact: true }).click(); await expect(notes.getByRole("region", { name: "Selected Work export", exact: true })).toHaveCount(0);
});

for (const status of [401, 403, 409]) test(`fresh report refusal ${status} clears private state without a file`, async ({ page }) => {
  await page.clock.install(); const { panel } = await open(page); let downloads = 0; page.on("download", () => downloads++);
  await page.route("**/notes/export", route => route.fulfill({ status, json: { detail: "Synthetic injected authorization or stale-review refusal" } }));
  await panel.getByRole("checkbox", { name: ack, exact: true }).check(); await panel.getByRole("button", { name: "Download reviewed work report", exact: true }).click();
  await expect(panel).toHaveCount(0); if (status === 401) await expect(page.getByLabel("Username", { exact: true })).toBeVisible(); else await expect(page.getByRole("alert")).toBeVisible(); expect(downloads).toBe(0);
});

test("cancelling a held actual backend report response suppresses late download", async ({ page }) => {
  await page.clock.install(); const { panel } = await open(page);
  let release!: () => void, arrived!: () => void; const hold = new Promise<void>(r => { release = r; }), seen = new Promise<void>(r => { arrived = r; });
  await page.route("**/notes/export", async route => { const response = await route.fetch(); arrived(); await hold; await route.fulfill({ response }).catch(() => {}); });
  let downloads = 0; page.on("download", () => downloads++); await panel.getByRole("checkbox", { name: ack, exact: true }).check(); await panel.getByRole("button", { name: "Download reviewed work report", exact: true }).click(); await seen;
  await panel.getByRole("button", { name: "Cancel work review request", exact: true }).click(); release(); await expect(panel).toHaveCount(0); await page.waitForTimeout(150); expect(downloads).toBe(0);
});

test("expiry and navigation remove selected private report state", async ({ page }) => {
  await page.clock.install(); const { panel, notes } = await open(page); await panel.getByLabel("Report title", { exact: true }).fill("Ephemeral sample status");
  await page.clock.fastForward(61000); await expect(panel).toHaveCount(0); await expect(notes).not.toContainText("Ephemeral sample status");
  await notes.getByRole("button", { name: "Open synthetic notes", exact: true }).click(); await notes.getByRole("button", { name: "Review work and prepare a report", exact: true }).click();
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Memory", exact: true }).click(); await expect(panel).toHaveCount(0);
});
