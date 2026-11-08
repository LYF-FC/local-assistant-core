import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { openSyntheticSession } from "./work-browser-session";

test.skip(process.env.BUTLER_WORK_NOTES_BROWSER_TESTS !== "1", "Optional synthetic interface overlay required");
test.use({ timezoneId: "UTC" });
const ack = "I will manage the meeting copy and its retention";
const names = ["meeting-action-owned", "meeting-action-unknown", "meeting-decision", "meeting-question", "meeting-observation"];
async function open(page: Page) {
  await openSyntheticSession(page, "browser-work-meeting");
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Work Companion", exact: true }).click();
  await page.getByRole("button", { name: "Load assigned workspaces", exact: true }).click();
  await page.getByRole("button", { name: "synthetic-adapter-ci", exact: true }).click();
  const notes = page.getByRole("region", { name: "Synthetic Work notes", exact: true });
  const response = page.waitForResponse(value => value.url().endsWith("/notes/catalogue"));
  await notes.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  const catalogue = await (await response).json();
  await notes.getByRole("button", { name: "Prepare a meeting", exact: true }).click();
  return { notes, checked_at: catalogue.checked_at };
}
async function prepare(page: Page, checked_at: string, selected = names) {
  const panel = page.getByRole("region", { name: "Sample meeting workbench", exact: true });
  for (const label of selected) await panel.getByRole("checkbox", { name: `Meeting note ${label}`, exact: true }).check();
  await panel.getByLabel("Meeting title", { exact: true }).fill("Sample weekly meeting");
  const when = new Date(Date.parse(checked_at) + 30 * 60000).toISOString().slice(0, 16);
  await panel.getByLabel("Meeting time (optional)", { exact: true }).fill(when);
  const response = page.waitForResponse(value => value.url().endsWith("/notes/export") && value.request().postDataJSON().purpose === "preview");
  await panel.getByRole("button", { name: "Preview meeting brief", exact: true }).click();
  const reviewed = await (await response).json();
  await expect(panel.getByRole("region", { name: "Reviewed meeting brief", exact: true })).toBeVisible();
  return { panel, reviewed };
}

test("actual confirmed agenda, unknown follow-ups and source/version citations produce a fresh reviewed Markdown copy", async ({ page }) => {
  test.setTimeout(60000); await page.clock.install();
  const { notes, checked_at } = await open(page), calls: Record<string, unknown>[] = [];
  page.on("request", request => { if (request.url().endsWith("/notes/export")) calls.push(request.postDataJSON()); });
  const { panel, reviewed } = await prepare(page, checked_at);
  await expect(panel.getByRole("checkbox", { name: "Meeting note export-draft", exact: true })).toHaveCount(0);
  for (const label of ["Actions and follow-ups", "Decisions", "Questions", "Observations"]) await expect(panel.getByRole("region", { name: `Meeting ${label}`, exact: true })).toBeVisible();
  await expect(panel).toContainText("Owner: meeting-owner");
  await expect(panel).toContainText("Completion: Unknown");
  await expect(panel.getByRole("region", { name: "Meeting Actions and follow-ups", exact: true })).toContainText("Due by meeting");
  await panel.getByText("Sources and versions", { exact: true }).click();
  await expect(panel).toContainText(reviewed.bundle.items[0].item.id);
  await panel.getByText("Sources and versions", { exact: true }).click();
  await expect(panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: "test-results/work-meeting-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/work-meeting-mobile.png", fullPage: true });
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  const downloaded = page.waitForEvent("download"), response = page.waitForResponse(value => value.url().endsWith("/notes/export") && value.request().postDataJSON().purpose === "download");
  await panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true }).click();
  const file = await downloaded, fresh = await (await response).json(), text = readFileSync((await file.path())!, "utf8");
  expect(fresh.bundle.export_id).not.toBe(reviewed.bundle.export_id);
  expect(text).toContain(`Export reference: \`${fresh.bundle.export_id}\``);
  expect(text).not.toContain(reviewed.bundle.export_id);
  expect(text).toContain("Title: Sample weekly meeting"); expect(text).toContain("Completion: Unknown");
  expect(text).toContain(`Source: container\\-adapter (\`${fresh.bundle.items[0].item.source_ids[0]}\`)`);
  expect(text).toContain("[^N5]"); expect(text).not.toContain("payload_hash");
  expect(file.suggestedFilename()).toBe(`butler-work-meeting-${fresh.bundle.workspace_id}-${fresh.bundle.export_id}.md`);
  expect(calls).toHaveLength(2); expect(calls[1]).toMatchObject({ include_drafts: false, purpose: "download", acknowledge_copy_limits: true, reviewed_hash: reviewed.reviewed_hash });
  expect(JSON.stringify(calls)).not.toContain("Sample weekly meeting");
  await expect(panel).toHaveCount(0); await expect(notes).toContainText("A meeting Markdown download was requested");
});

test("meeting annotation and selection changes invalidate review and acknowledgement", async ({ page }) => {
  await page.clock.install(); const { checked_at } = await open(page), { panel } = await prepare(page, checked_at);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  await panel.getByLabel("Meeting title", { exact: true }).fill("Revised sample meeting");
  await expect(panel.getByRole("region", { name: "Reviewed meeting brief", exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: "Preview meeting brief", exact: true }).click();
  await expect(panel.getByRole("checkbox", { name: ack, exact: true })).not.toBeChecked();
  await panel.getByRole("checkbox", { name: "Meeting note meeting-question", exact: true }).uncheck();
  await expect(panel.getByRole("region", { name: "Reviewed meeting brief", exact: true })).toHaveCount(0);
});

for (const status of [409, 401]) test(`fresh download ${status} clears meeting content and never produces a file`, async ({ page }) => {
  await page.clock.install(); const { checked_at } = await open(page), { panel } = await prepare(page, checked_at);
  let downloads = 0; page.on("download", () => downloads++);
  await page.route("**/notes/export", route => route.fulfill({ status, json: { detail: "Synthetic injected conflict or access denial" } }));
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  await panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true }).click();
  await expect(panel).toHaveCount(0); await expect(page.getByText("Sample weekly meeting", { exact: true })).toHaveCount(0);
  if (status === 401) await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
  else await expect(page.getByRole("alert")).toContainText("changed");
  expect(downloads).toBe(0);
});

test("cancelling a held real-API download suppresses a late valid response", async ({ page }) => {
  await page.clock.install(); const { checked_at } = await open(page), { panel } = await prepare(page, checked_at);
  let release!: () => void, arrived!: () => void;
  const hold = new Promise<void>(resolve => { release = resolve; }), seen = new Promise<void>(resolve => { arrived = resolve; });
  await page.route("**/notes/export", async route => { const response = await route.fetch(); arrived(); await hold; await route.fulfill({ response }).catch(() => {}); });
  let downloads = 0; page.on("download", () => downloads++);
  await panel.getByRole("checkbox", { name: ack, exact: true }).check();
  await panel.getByRole("button", { name: "Download reviewed meeting Markdown", exact: true }).click(); await seen;
  await panel.getByRole("button", { name: "Cancel meeting request", exact: true }).click(); release();
  await expect(panel).toHaveCount(0); await page.waitForTimeout(150); expect(downloads).toBe(0);
});

test("snapshot expiry and navigation unmount clear the meeting workbench", async ({ page }) => {
  await page.clock.install(); const { notes, checked_at } = await open(page); await prepare(page, checked_at);
  await page.clock.fastForward(61000);
  await expect(page.getByRole("region", { name: "Sample meeting workbench", exact: true })).toHaveCount(0);
  await expect(notes).not.toContainText("meeting-action-owned");
  await notes.getByRole("button", { name: "Open synthetic notes", exact: true }).click();
  await notes.getByRole("button", { name: "Prepare a meeting", exact: true }).click();
  await prepare(page, checked_at, ["meeting-question"]);
  await page.getByRole("navigation", { name: "Local records" }).getByRole("button", { name: "Memory", exact: true }).click();
  await expect(page.getByRole("region", { name: "Sample meeting workbench", exact: true })).toHaveCount(0);
});
