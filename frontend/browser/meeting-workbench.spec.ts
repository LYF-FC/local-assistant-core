import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { archive, record, workspace } from "../src/test-support/work-meeting";
import type { ExportRequest, NotesArchive } from "../src/work-notes-api";
const ack = "I will manage the meeting copy and its retention";
const items = [record(1, "question"), record(2, "action"), record(3, "decision"), record(4, "observation"), record(5, "action")];
items[1].item.due_at = "2026-11-07T10:30:00Z";
const features = { capture: true, review: true, confirmation: true, changes: true, export: true };
const frame = { schema_version: 1, model_invoked: false, execution_allowed: false, real_ingestion_allowed: false, workspace_id: workspace, checked_at: "2026-11-07T10:00:00Z", valid_until: "2026-11-07T10:01:00Z", features };
async function mock(page: Page) {
  const calls: ExportRequest[] = [];
  let serial = 0;
  await page.route("**/api/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (!path.includes(workspace)) return route.fulfill({ status: 404, json: { detail: "Synthetic test workspace unavailable" } });
    if (path.endsWith("/notes/catalogue")) return route.fulfill({ json: { ...frame, mode: "synthetic_notes_catalogue", pages: { notes: { items: [...items.map(({ item }) => ({ id: item.id, revision: item.revision, state: item.state, label: item.marker.slice(10), content_available: true, retain_until: item.retain_until })), { id: "d0000000-0000-4000-8000-000000000001", revision: 1, state: "draft", label: "Unconfirmed sample", content_available: true, retain_until: "2026-11-08T10:00:00Z" }], next_cursor: null }, sources: { items: [], next_cursor: null }, parties: { items: [], next_cursor: null }, policies: { items: [], next_cursor: null }, requests: { items: [], next_cursor: null, pending_count: 0 } } } });
    if (path.endsWith("/notes/export")) {
      const body = request.postDataJSON() as ExportRequest; calls.push(body);
      expect(body.include_drafts).toBe(false);
      expect(request.headers()["x-csrf-token"]).toContain("synthetic-component-csrf-");
      const bundle: NotesArchive = { ...archive(body.selections.map(selected => items.find(entry => entry.item.id === selected.id)!)), export_id: `60000000-0000-4000-8000-${String(++serial).padStart(12, "0")}` };
      return route.fulfill({ json: { ...frame, mode: "synthetic_notes_export", bundle, bundle_bytes: new TextEncoder().encode(JSON.stringify(bundle)).length, reviewed_hash: "a".repeat(64), purpose: body.purpose } });
    }
    return route.fulfill({ status: 503, json: { detail: "Unhandled synthetic fixture path" } });
  });
  await page.goto("/test-harness/meeting.html");
  await page.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  await page.getByRole("button", { name: "Prepare a meeting", exact: true }).click();
  return calls;
}
async function prepare(page: Page, names = ["Sample note 1", "Sample note 2", "Sample note 3", "Sample note 4", "Sample note 5"]) {
  const panel = page.getByRole("region", { name: "Sample meeting workbench", exact: true });
  for (const name of names) await panel.getByRole("checkbox", { name: `Meeting note ${name}`, exact: true }).check();
  await panel.getByLabel("Meeting title", { exact: true }).fill("Sample weekly review");
  await panel.getByLabel("Meeting time (optional)", { exact: true }).fill("2026-11-07T11:00");
  await panel.getByRole("button", { name: "Preview meeting brief", exact: true }).click();
  await expect(panel.getByRole("region", { name: "Reviewed meeting brief", exact: true })).toBeVisible();
  return panel;
}

test("groups explicit notes, unknown follow-ups and citations, then downloads only a fresh reviewed copy", async ({ page }) => {
  const keyWarnings: string[] = [];
  page.on("console", message => { if (message.type() === "error" && /same key|unique.*key/i.test(message.text())) keyWarnings.push(message.text()); });
  const calls = await mock(page), panel = await prepare(page);
  await expect(panel.getByRole("checkbox", { name: "Meeting note Unconfirmed sample", exact: true })).toHaveCount(0);
  await expect(panel.getByRole("region", { name: "Selected action follow-ups", exact: true })).toContainText("2");
  await expect(panel.getByRole("region", { name: "Meeting Actions and follow-ups", exact: true })).toContainText("Due by meeting");
  await expect(panel).toContainText("Completion: Unknown");
  await panel.getByText("Sources and versions", { exact: true }).click();
  await expect(panel).toContainText(items[0].item.id);
  await panel.getByText("Sources and versions", { exact: true }).click();
  await expect(panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: "test-results/work-meeting-local-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/work-meeting-local-mobile.png", fullPage: true });
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  const file = page.waitForEvent("download");
  await panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true }).click();
  const download = await file, text = readFileSync((await download.path())!, "utf8");
  expect(text).toContain("Title: Sample weekly review"); expect(text).toContain("[^N1]");
  expect(text).toContain(`Source: Sample source (\`${items[0].item.source_ids[0]}\`)`);
  expect(text).toContain("60000000-0000-4000-8000-000000000002");
  expect(download.suggestedFilename()).toBe(`butler-work-meeting-${workspace}-60000000-0000-4000-8000-000000000002.md`);
  expect(calls).toHaveLength(2); expect(calls[1]).toMatchObject({ purpose: "download", include_drafts: false, acknowledge_copy_limits: true, reviewed_hash: "a".repeat(64) });
  expect(JSON.stringify(calls)).not.toContain("Sample weekly review");
  await expect(page.getByRole("region", { name: "Sample meeting workbench", exact: true })).toHaveCount(0);
  expect(keyWarnings).toEqual([]);
});

test("edits invalidate the reviewed contents and acknowledgement", async ({ page }) => {
  const calls = await mock(page), panel = await prepare(page, ["Sample note 1"]);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  await panel.getByLabel("Meeting title", { exact: true }).fill("Changed sample meeting");
  await expect(panel.getByRole("region", { name: "Reviewed meeting brief", exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: "Preview meeting brief", exact: true }).click();
  await expect(panel.getByRole("checkbox", { name: ack, exact: true })).not.toBeChecked();
  expect(calls).toHaveLength(2);
});

test("a denial of the fresh download clears private preview without a file", async ({ page }) => {
  await mock(page); const panel = await prepare(page);
  let downloads = 0; page.on("download", () => downloads++);
  await page.route("**/notes/export", route => route.fulfill({ status: 409, json: { detail: "Synthetic stale review" } }));
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  await panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true }).click();
  await expect(panel).toHaveCount(0); await expect(page.getByRole("alert")).toContainText("changed");
  await expect(page.getByRole("region", { name: "Synthetic Work notes", exact: true })).not.toContainText("Sample note 1");
  expect(downloads).toBe(0);
});

test("expiry and workspace/session unmount erase the meeting snapshot", async ({ page }) => {
  await page.clock.install(); await mock(page); await prepare(page);
  await page.clock.fastForward(61000);
  await expect(page.getByRole("region", { name: "Sample meeting workbench", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Synthetic Work notes", exact: true })).not.toContainText("Sample weekly review");
  await page.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  await page.getByRole("button", { name: "Prepare a meeting", exact: true }).click(); await prepare(page, ["Sample note 1"]);
  await page.getByRole("button", { name: "Reset test session", exact: true }).click();
  await expect(page.getByRole("region", { name: "Sample meeting workbench", exact: true })).toHaveCount(0);
});

test("closing a pending preview or download suppresses late private content and file creation", async ({ page }) => {
  await mock(page); const panel = await prepare(page, ["Sample note 1"]);
  let release!: () => void, arrived!: () => void;
  const hold = new Promise<void>(resolve => { release = resolve; }), seen = new Promise<void>(resolve => { arrived = resolve; });
  await page.route("**/notes/export", async route => {
    const bundle = { ...archive([items[0]]), export_id: "70000000-0000-4000-8000-000000000001" };
    arrived(); await hold;
    await route.fulfill({ json: { ...frame, mode: "synthetic_notes_export", bundle, bundle_bytes: new TextEncoder().encode(JSON.stringify(bundle)).length, reviewed_hash: "a".repeat(64), purpose: "download" } }).catch(() => {});
  });
  let downloads = 0; page.on("download", () => downloads++);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  await panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true }).click(); await seen;
  await panel.getByRole("button", { name: "Cancel meeting request", exact: true }).click(); release();
  await expect(panel).toHaveCount(0); await page.waitForTimeout(100); expect(downloads).toBe(0);
});
