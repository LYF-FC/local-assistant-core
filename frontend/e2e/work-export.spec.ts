import { openSyntheticSession } from "./work-browser-session";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";

test.skip(process.env.BUTLER_WORK_NOTES_BROWSER_TESTS !== "1", "Optional synthetic interface overlay required");
async function open(page: Page) {
  await openSyntheticSession(page, "browser-work-export");
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Work Companion", exact: true }).click();
  await page.getByRole("button", { name: "Load assigned workspaces", exact: true }).click();
  await page.getByRole("button", { name: "synthetic-adapter-ci", exact: true }).click();
  const panel = page.getByRole("region", { name: "Synthetic Work notes", exact: true });
  await panel.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  await expect(panel.getByRole("button", { name: "Export selected notes", exact: true })).toBeEnabled();
  return panel;
}
async function preview(page: Page) {
  await page.getByRole("button", { name: "Export selected notes", exact: true }).click();
  const panel = page.getByRole("region", { name: "Selected Work export", exact: true });
  await panel.getByRole("checkbox", { name: "Export tls-review", exact: true }).check();
  await panel.getByRole("button", { name: "Preview selected export", exact: true }).click();
  await expect(panel.getByRole("region", { name: "Reviewed export preview", exact: true })).toBeVisible();
  return panel;
}
const ack = "I will manage the downloaded copy and its retention";

test("selected confirmed and explicitly included draft records download only after review and fresh checks", async ({ page }) => {
  test.setTimeout(60000);
  await page.clock.install();
  const notes = await open(page);
  const calls: { purpose: string; reviewed_hash?: string; acknowledge_copy_limits?: boolean }[] = [];
  page.on("request", request => { if (request.url().endsWith("/notes/export")) calls.push(request.postDataJSON()); });
  let downloads = 0; page.on("download", () => { downloads++; });
  const panel = await preview(page);
  await expect(panel.getByRole("checkbox", { name: "Export export-draft", exact: true })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Download reviewed JSON", exact: true })).toBeDisabled();
  await panel.getByRole("checkbox", { name: "Include unconfirmed drafts", exact: true }).check();
  await expect(panel.getByRole("region", { name: "Reviewed export preview", exact: true })).toHaveCount(0);
  await expect(panel.getByRole("checkbox", { name: "Export tls-review", exact: true })).not.toBeChecked();
  await panel.getByRole("checkbox", { name: "Export tls-review", exact: true }).check();
  await panel.getByRole("checkbox", { name: "Export export-draft", exact: true }).check();
  const prepared = page.waitForResponse(r => r.url().endsWith("/notes/export") && r.request().postDataJSON().purpose === "preview");
  await panel.getByRole("button", { name: "Preview selected export", exact: true }).click();
  const reviewed = await (await prepared).json();
  const detail = panel.getByRole("region", { name: "Reviewed export preview", exact: true });
  await expect(detail).toContainText("2 selected notes");
  await expect(detail).toContainText("Unknown");
  await expect(detail).toContainText("Butler cannot erase it");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/work-export-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: "test-results/work-export-desktop.png", fullPage: true });
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  const file = page.waitForEvent("download");
  const fresh = page.waitForResponse(r => r.url().endsWith("/notes/export") && r.request().postDataJSON().purpose === "download");
  await panel.getByRole("button", { name: "Download reviewed JSON", exact: true }).click();
  const download = await file, response = await (await fresh).json();
  const path = await download.path(); expect(path).not.toBeNull();
  const bundle = JSON.parse(readFileSync(path!, "utf8"));
  expect(bundle.export_id).toBe(response.bundle.export_id);
  expect(bundle.export_id).not.toBe(reviewed.bundle.export_id);
  expect(bundle.workspace_id).toBe(reviewed.workspace_id);
  expect(bundle.items).toHaveLength(2);
  expect(bundle.items.map((v: { item: { state: string } }) => v.item.state).sort()).toEqual(["confirmed", "draft"]);
  expect(bundle.items.every((v: { item: { owner_id: unknown; due_at: unknown }; references: { sources: unknown[] } }) => v.item.owner_id === null && v.item.due_at === null && v.references.sources.length > 0)).toBe(true);
  expect(bundle.managed_copy).toBe(false); expect(bundle.current_revisions_only).toBe(true); expect(bundle.raw_transcripts_included).toBe(false);
  expect(JSON.stringify(bundle)).not.toContain("payload_hash");
  expect(download.suggestedFilename()).toBe(`butler-work-${bundle.workspace_id}-${bundle.export_id}.json`);
  expect(calls.map(c => c.purpose)).toEqual(["preview", "preview", "download"]);
  expect(calls[2]).toMatchObject({ reviewed_hash: reviewed.reviewed_hash, acknowledge_copy_limits: true });
  expect(downloads).toBe(1);
  await expect(notes).toContainText("A JSON download was requested");
  await preview(page);
  await page.clock.fastForward(61000);
  await expect(notes.getByRole("region", { name: "Selected Work export", exact: true })).toHaveCount(0);
  await expect(notes).not.toContainText("tls-review");
  expect(downloads).toBe(1);
});

test("cancel, denied fresh read and navigation prevent late file creation", async ({ page }) => {
  test.setTimeout(90000);
  const notes = await open(page);
  let downloads = 0; page.on("download", () => { downloads++; });
  let panel = await preview(page);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  let release!: () => void, reached!: () => void;
  let hold = new Promise<void>(resolve => { release = resolve; });
  let started = new Promise<void>(resolve => { reached = resolve; });
  await page.route("**/notes/export", async route => {
    if (route.request().postDataJSON().purpose !== "download") { await route.continue(); return; }
    const response = await route.fetch(); reached(); await hold;
    try { await route.fulfill({ response }); } catch { /* cancelled read */ }
  });
  await panel.getByRole("button", { name: "Download reviewed JSON", exact: true }).click();
  await started;
  await panel.getByRole("button", { name: "Cancel export request", exact: true }).click();
  release();
  await expect(panel).toHaveCount(0);
  await page.unroute("**/notes/export");
  expect(downloads).toBe(0);
  panel = await preview(page);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  await page.route("**/notes/export", route => route.fulfill({ status: 403, json: { detail: "Denied" } }));
  await panel.getByRole("button", { name: "Download reviewed JSON", exact: true }).click();
  await expect(notes.getByRole("alert")).toBeVisible();
  await expect(panel).toHaveCount(0);
  await expect(notes).not.toContainText("tls-review");
  expect(downloads).toBe(0);
  await page.unroute("**/notes/export");
  await notes.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  panel = await preview(page);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  hold = new Promise<void>(resolve => { release = resolve; });
  started = new Promise<void>(resolve => { reached = resolve; });
  await page.route("**/notes/export", async route => {
    const response = await route.fetch(); reached(); await hold;
    try { await route.fulfill({ response }); } catch { /* view changed */ }
  });
  await panel.getByRole("button", { name: "Download reviewed JSON", exact: true }).click();
  await started;
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Memory", exact: true }).click();
  release();
  await expect(notes).toHaveCount(0);
  expect(downloads).toBe(0);
});
