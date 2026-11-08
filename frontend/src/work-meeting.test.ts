import { describe, expect, it } from "vitest";
import { meetingBrief, meetingOptions, MeetingError } from "./work-meeting";

import { archive, record } from "./test-support/work-meeting";
const owner = "33333333-3333-4333-8333-333333333333";

describe("selected meeting agenda", () => {
  it("preserves citations/selection order while grouping known kinds", () => {
    const items = [record(1, "question"), record(2), record(3, "decision"), record(4), record(5, "observation")];
    const brief = meetingBrief(archive(items), meetingOptions(" Sample review ", null));
    expect(brief.options).toEqual({ title: "Sample review", starts_at: null });
    expect(brief.selected.map(n => n.citation)).toEqual(["N1", "N2", "N3", "N4", "N5"]);
    expect(brief.sections.map(s => [s.kind, s.notes.map(n => n.citation)])).toEqual([["action", ["N2", "N4"]], ["decision", ["N3"]], ["question", ["N1"]], ["observation", ["N5"]]]);
    expect(brief.actions.total).toBe(2);
  });
  it("compares due dates only with explicit meeting time including equality", () => {
    const items = [record(1), record(2), record(3), record(4, "decision")];
    items[0].item.due_at = "2026-11-07T09:00:00Z";
    items[1].item.due_at = "2026-11-07T13:00:00+02:00";
    items[3].item.due_at = "2026-11-07T08:00:00Z";
    const brief = meetingBrief(archive(items), meetingOptions("Sample", "2026-11-07T12:00:00+02:00"));
    expect(brief.options.starts_at).toBe("2026-11-07T10:00:00.000Z");
    expect(brief.actions).toMatchObject({ total: 3, by_meeting: 1, after_meeting: 1, unknown_due: 1, unknown_meeting: 0 });
    items[0].item.due_at = "2026-11-07T10:00:00Z";
    expect(meetingBrief(archive(items), brief.options).selected[0].due_relation).toBe("by_meeting");
    const unknown = meetingBrief(archive(items), meetingOptions("Sample", null));
    expect(unknown.actions).toMatchObject({ by_meeting: 0, after_meeting: 0, unknown_due: 1, unknown_meeting: 2 });
  });
  it("keeps owner and completion unknown instead of inferring from text", () => {
    const items = [record(1), record(2), record(3)];
    items[0].item.marker = "synthetic:Done by Member A on Monday";
    items[1].item.owner_id = owner; items[1].references.owner = { id: owner, label: null, available: false };
    items[2].item.owner_id = owner; items[2].references.owner = { id: owner, label: "Sample owner", available: true };
    const brief = meetingBrief(archive(items), meetingOptions("Sample", null));
    expect(brief.selected.map(n => n.owner)).toEqual(["Unknown", "Previous owner unavailable", "Sample owner"]);
    expect(brief.actions).toMatchObject({ unknown_owner: 1, unavailable_owner: 1, unknown_due: 3 });
    expect(brief.selected[0]).not.toHaveProperty("completed");
  });
  it.each(["", "x".repeat(121), "<script>bad</script>", "Sample\nother", "Question: unexpected"])("rejects invalid title %s", title => {
    expect(() => meetingOptions(title, null)).toThrow(MeetingError);
  });
  it.each(["invalid", "2026-11-07T10:00:00", "2026-99-99T10:00:00Z"])("rejects ambiguous/invalid time %s", date => {
    expect(() => meetingOptions("Sample", date)).toThrow(MeetingError);
  });
  it.each(["draft", "workspace", "sources", "source_label", "owner", "duplicate", "empty", "capacity", "managed", "retention", "marker", "unreviewed", "flags"])("refuses unsafe snapshot %s", fault => {
    const value = archive();
    if (fault === "draft") value.items[0].item.state = "draft";
    if (fault === "workspace") value.items[0].item.workspace_id = owner;
    if (fault === "sources") value.items[0].references.sources = [];
    if (fault === "source_label") value.items[0].references.sources[0].label = "<unsafe>";
    if (fault === "owner") value.items[0].references.owner = { id: owner, label: "Invented", available: true };
    if (fault === "duplicate") value.items.push(value.items[0]);
    if (fault === "empty") value.items = [];
    if (fault === "capacity") value.items = Array.from({ length: 11 }, (_, n) => record(n + 1));
    if (fault === "managed") Object.assign(value, { managed_copy: true });
    if (fault === "retention") value.items[0].item.retain_until = "2026-11-07T10:00:00Z";
    if (fault === "marker") value.items[0].item.marker = "other:private";
    if (fault === "unreviewed") value.drafts_permitted = true;
    if (fault === "flags") Object.assign(value, { execution_allowed: true });
    expect(() => meetingBrief(value, meetingOptions("Sample", null))).toThrow(MeetingError);
  });
});
