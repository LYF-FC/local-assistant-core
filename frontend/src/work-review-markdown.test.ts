import { expect, it } from "vitest";
import { archive, record } from "./test-support/work-meeting";
import { defaultReviewOptions } from "./work-review";
import { reviewMarkdown } from "./work-review-markdown";
it("projects only visible notes with stable citations and fresh export/retention/scope provenance", () => {
  const value = archive([record(1), record(2, "question"), record(3, "decision")]), options = { ...defaultReviewOptions(value.generated_at), kind: "question" as const };
  const result = reviewMarkdown(value, options);
  expect(result.text).toContain("Coverage: 1 visible of 3"); expect(result.text).toContain("[^N2]"); expect(result.text).not.toContain("[^N1]"); expect(result.text).not.toContain(value.items[0].item.id); expect(result.text).toContain(`Note \`${value.items[1].item.id}\`, version 2`);
  expect(result.text).toContain(`Export reference: \`${value.export_id}\``); expect(result.text).toContain("Copy retention ends: 2026-11-08"); expect(result.text).toContain("Completion is Unknown"); expect(result.text).toContain("not event history"); expect(result.text).toContain("start inclusive/end exclusive");
  expect(result.filename).toBe(`butler-work-report-${value.workspace_id}-${value.export_id}.md`); expect(result.bytes).toBe(new TextEncoder().encode(result.text).length);
});
it("escapes dynamic title, marker and query without inserting links or HTML", () => {
  const value = archive(); value.items[0].item.marker = "synthetic:Sample _note_.";
  const result = reviewMarkdown(value, { ...defaultReviewOptions(value.generated_at), title: "Sample _report_.", query: "_note_" });
  expect(result.text).toContain("Title: Sample \\_report\\_\\."); expect(result.text).toContain("Text query: \\_note\\_"); expect(result.text).toContain("Sample \\_note\\_\\."); expect(result.text).toContain(`Source: Sample source (\`${value.items[0].item.source_ids[0]}\`)`);
});
it("refuses empty projections rather than downloading misleading reports", () => { const value = archive(); expect(() => reviewMarkdown(value, { ...defaultReviewOptions(value.generated_at), query: "absent" })).toThrow("No notes match"); });
it("refuses oversized reports without truncating provenance", () => {
  const value = archive(Array.from({ length: 10 }, (_, i) => record(i + 1)));
  value.items.forEach(note => { note.item.marker = "synthetic:" + "_".repeat(246); note.item.owner_id = "33333333-3333-4333-8333-333333333333"; note.references.owner = { id: note.item.owner_id, available: true, label: "_".repeat(246) }; note.item.source_ids = Array.from({ length: 10 }, (_, i) => `b0000000-0000-4000-8000-${String(i).padStart(12, "0")}`); note.references.sources = note.item.source_ids.map(id => ({ id, label: "_".repeat(246) })); });
  expect(() => reviewMarkdown(value, defaultReviewOptions(value.generated_at))).toThrow("too large");
});
