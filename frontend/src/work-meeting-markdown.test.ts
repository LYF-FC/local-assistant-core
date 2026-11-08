import { expect, it } from "vitest";
import { archive, record } from "./test-support/work-meeting";
import { meetingMarkdown, markdownText } from "./work-meeting-markdown";

it("creates a cited bounded document from the fresh export with copy retention", () => {
  const value = archive([record(1, "question"), record(2, "action"), record(3, "decision")]);
  const result = meetingMarkdown(value, { title: "Sample agenda", starts_at: "2026-11-07T11:00:00Z" });
  expect(result.text).toContain("# Sample meeting brief\n");
  expect(result.text).toContain("Copy retention ends: 2026-11-08T10:00:00.000Z");
  expect(result.text).toContain(`Export reference: \`${value.export_id}\``);
  expect(result.text).toContain("## Actions and follow-ups\n\n- Sample note 2 [^N2]");
  expect(result.text).toContain(`[^N1]: Note \`${value.items[0].item.id}\`, version 2.`);
  expect(result.text).toContain(`Source: Sample source (\`${value.items[0].item.source_ids[0]}\`)`);
  expect(result.text).toContain("Completion: Unknown");
  expect(result.text).toContain("No selected notes in this section.");
  expect(result.text).not.toContain("payload_hash");
  expect(result.bytes).toBe(new TextEncoder().encode(result.text).length);
  expect(result.filename).toBe(`butler-work-meeting-${value.workspace_id}-${value.export_id}.md`);
});
it("escapes dynamic Markdown punctuation and never emits active links or HTML", () => {
  expect(markdownText("<tag> [link](target) _bold_ `code` # + - . ! | ~ \\")).toBe("\\<tag\\> \\[link\\]\\(target\\) \\_bold\\_ \\`code\\` \\# \\+ \\- \\. \\! \\| \\~ \\\\");
  const value = archive(); value.items[0].item.marker = "synthetic:_Sample_. - agenda"; value.items[0].references.sources[0].label = "Source_one.md";
  const result = meetingMarkdown(value, { title: "_Sample_. - meeting", starts_at: null });
  expect(result.text).toContain("Title: \\_Sample\\_\\. \\- meeting");
  expect(result.text).toContain("Source: Source\\_one\\.md");
  expect(result.text).toContain("Meeting time: Unknown");
  expect(result.text).toContain("Not assessed - meeting time Unknown");
});
it("shows the actual retention conflict instead of extending it to the meeting", () => {
  const result = meetingMarkdown(archive(), { title: "Sample", starts_at: "2026-11-09T10:00:00Z" });
  expect(result.text).toContain("at or after this copy's retention boundary");
  expect(result.text).toContain("Copy retention ends: 2026-11-08T10:00:00.000Z");
});
it("rejects unsafe records and oversized Markdown without truncation", () => {
  const bad = archive(); bad.items[0].item.state = "draft";
  expect(() => meetingMarkdown(bad, { title: "Sample", starts_at: null })).toThrow();
  const large = archive(Array.from({ length: 10 }, (_, index) => record(index + 1)));
  for (const entry of large.items) {
    entry.item.marker = "synthetic:" + "_".repeat(246);
    entry.item.source_ids = Array.from({ length: 10 }, (_, index) => `b0000000-0000-4000-8000-${String(index).padStart(12, "0")}`);
    entry.references.sources = entry.item.source_ids.map(id => ({ id, label: "_".repeat(246) }));
    entry.item.owner_id = "c0000000-0000-4000-8000-000000000000";
    entry.references.owner = { id: entry.item.owner_id, available: true, label: "_".repeat(246) };
  }
  expect(() => meetingMarkdown(large, { title: "Sample", starts_at: null })).toThrow("too large");
});
