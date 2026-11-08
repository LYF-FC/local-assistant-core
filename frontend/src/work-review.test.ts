import { describe, expect, it } from "vitest";
import { defaultReviewOptions, reviewOptions, workReview } from "./work-review";
import { archive, record } from "./test-support/work-meeting";
const owner = "33333333-3333-4333-8333-333333333333", second = "77777777-7777-4777-8777-777777777777";
const opts = () => defaultReviewOptions("2026-11-07T10:00:00Z");
function sample() {
  const items = [record(1), record(2), record(3), record(4, "decision"), record(5, "question"), record(6, "observation")];
  items[0].item.due_at = "2026-11-07T09:59:59Z"; items[1].item.due_at = "2026-11-07T10:00:00Z"; items[2].item.due_at = "2026-11-14T10:00:00Z";
  items[0].item.owner_id = owner; items[0].references.owner = { id: owner, label: "Sample owner", available: true };
  items[1].item.owner_id = second; items[1].references.owner = { id: second, label: "Sample owner", available: true };
  return archive(items);
}
describe("selected professional review", () => {
  it("classifies due buckets relative to server snapshot with exact half-open boundaries", () => {
    const result = workReview(sample(), opts());
    expect(result.selected.map(n => n.due)).toEqual(["past", "next7", "later", "not_action", "not_action", "not_action"]);
    expect(result.counts).toMatchObject({ actions: 3, decisions: 1, questions: 1, observations: 1, past: 1, next7: 1, unknown_owner: 4 });
    expect(result.selected[0]).not.toHaveProperty("completed");
  });
  it("pins due classification to the reviewed server time when download refreshes export metadata", () => {
    const value = sample(), before = workReview(value, opts());
    value.generated_at = "2026-11-07T10:00:30Z";
    expect(workReview(value, opts()).selected.map(n => n.due)).toEqual(before.selected.map(n => n.due));
    expect(() => workReview(value, { ...opts(), as_of: "2026-11-07T10:01:00Z" })).toThrow();
  });
  it("intersects query, kind, owner, source and due facets without inferring from text", () => {
    const value = sample(); value.items[0].item.marker = "synthetic:Done SAMPLE commitment";
    const options = { ...opts(), query: " sample commitment ", kind: "action" as const, owner, source: value.items[0].item.source_ids[0], due: "past" as const };
    const result = workReview(value, options);
    expect(result.visible.map(n => n.citation)).toEqual(["N1"]); expect(result.selected).toHaveLength(6); expect(result.counts.actions).toBe(1);
    expect(workReview(value, { ...options, due: "unknown" }).visible).toEqual([]);
  });
  it("keeps equal owner labels in distinct ID groups and unknown separate", () => {
    const result = workReview(sample(), opts());
    expect(result.owners.map(g => [g.id, g.notes.length])).toEqual([[owner, 1], [second, 1], ["unknown", 4]]);
    expect(workReview(sample(), { ...opts(), owner: second }).visible.map(n => n.citation)).toEqual(["N2"]);
  });
  it("separates unknown/unavailable owners and action due unknown from non-actions", () => {
    const value = sample(); value.items[0].references.owner = { id: owner, available: false, label: null }; value.items[2].item.due_at = null;
    expect(workReview(value, { ...opts(), owner: "unavailable" }).visible.map(n => n.citation)).toEqual(["N1"]);
    expect(workReview(value, { ...opts(), owner: "unknown", due: "unknown" }).visible.map(n => n.citation)).toEqual(["N3"]);
    expect(workReview(value, { ...opts(), due: "unknown" }).counts.unknown_due).toBe(1);
  });
  it("uses current record timestamps, inclusive start/exclusive end, without event-history inference", () => {
    const value = sample(); value.items[0].item.updated_at = "2026-11-06T00:00:00Z"; value.items[1].item.updated_at = "2026-11-07T00:00:00Z";
    const options = { ...opts(), from: "2026-11-06T00:00:00Z", until: "2026-11-07T00:00:00Z", activity: "updated" as const };
    expect(workReview(value, options).visible.map(n => n.citation)).toEqual(["N1"]); expect(workReview(value, { ...options, activity: "created" }).visible).toEqual([]);
  });
  it("sorts stably without changing original citations or mutating the archive", () => {
    const value = sample(); value.items[0].item.due_at = null; value.items[2].item.updated_at = "2026-11-06T00:00:00Z";
    expect(workReview(value, { ...opts(), sort: "due" }).visible.map(n => n.citation)).toEqual(["N2", "N3", "N1", "N4", "N5", "N6"]);
    expect(workReview(value, { ...opts(), sort: "updated" }).visible.map(n => n.citation)).toEqual(["N3", "N1", "N2", "N4", "N5", "N6"]); expect(value.items[0].item.id).toBe(record(1).item.id);
  });
  it("searches source/owner text while retaining source IDs as filter authority", () => {
    const value = sample(); value.items[1].item.source_ids = [second]; value.items[1].references.sources = [{ id: second, label: "Sample source" }];
    expect(workReview(value, { ...opts(), source: second, query: "sample owner" }).visible.map(n => n.citation)).toEqual(["N2"]); expect(workReview(value, { ...opts(), query: "missing" }).visible).toEqual([]);
  });
  it.each(["from", "until", "range", "wide", "query", "control", "kind", "owner", "source", "due", "activity", "sort", "created", "future", "draft", "unknown_owner_id", "unknown_source_id"])("refuses invalid or misleading input %s", fault => {
    const value = sample(), options = opts();
    if (fault === "from") options.from = "2026-11-01T00:00:00"; if (fault === "until") options.until = "bad"; if (fault === "range") options.from = options.until; if (fault === "wide") options.from = "2020-01-01T00:00:00Z";
    if (fault === "query") options.query = "x".repeat(121); if (fault === "control") options.query = "line\nnew";
    if (["kind", "due", "activity", "sort", "owner", "source"].includes(fault)) Object.assign(options, { [fault]: "invented" });
    if (fault === "created") value.items[0].item.created_at = "2026-11-03T00:00:00Z"; if (fault === "future") value.items[0].item.updated_at = "2026-11-08T00:00:00Z"; if (fault === "draft") value.items[0].item.state = "draft";
    if (fault === "unknown_owner_id") options.owner = "99999999-9999-4999-8999-999999999999"; if (fault === "unknown_source_id") options.source = owner;
    expect(() => workReview(value, options)).toThrow();
  });
  it("normalizes annotations and accepts the maximum exact window", () => { const options = opts(); options.from = "2025-11-06T10:00:00Z"; options.query = " sample "; expect(reviewOptions(options)).toMatchObject({ from: "2025-11-06T10:00:00.000Z", query: "sample" }); });
});
