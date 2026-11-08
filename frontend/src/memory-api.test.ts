import { afterEach, describe, expect, it, vi } from "vitest";
import { correctMemory, createMemory, exportMemory, forgetMemory, historyMemory, listMemory, parseEntry, parsePage, readMemory } from "./memory-api";
import type { ActiveMemory, Values } from "./memory-api";

const id = "11111111-1111-4111-8111-111111111111";
const owner = "22222222-2222-4222-8222-222222222222";
const values: Values = { title: "Synthetic", content: { text: "Synthetic text" }, source_type: "manual", source_reference: "Synthetic source", assessment: "confirmed", expires_at: null };
const entry: ActiveMemory = { id, owner_id: owner, scope: "member_a_private", kind: "preference", state: "active", revision: 1, created_at: "2026-11-04T00:00:00Z", updated_at: "2026-11-04T00:00:00Z", ...values, expired: false, eligible_for_context: true };
const filters = { scope: "member_a_private", kind: "preference", expired: true, forgotten: false };
const page = { schema_version: 1, generated_at: entry.created_at, items: [entry], next_cursor: null };
const response = (value: unknown) => new Response(JSON.stringify(value));
afterEach(() => vi.unstubAllGlobals());
describe("scoped memory client", () => {
  it("uses bounded same-origin no-store filtered reads and passes cancellation", async () => {
    const fetch = vi.fn().mockResolvedValue(response(page)); vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    expect((await listMemory(filters, controller.signal)).items[0]).toEqual(entry);
    expect(fetch).toHaveBeenCalledWith("/api/v1/memory?limit=25&scope=member_a_private&kind=preference&include_expired=true", expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error", signal: controller.signal }));
  });
  it("sends immutable create scope/kind and current revision/CSRF on writes", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(response(entry))); vi.stubGlobal("fetch", fetch);
    const signal = new AbortController().signal;
    await createMemory(values, "member_a_private", "preference", "synthetic-csrf", signal);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ ...values, scope: "member_a_private", kind: "preference" });
    const structured = { ...entry, content: { camera: "synthetic", tags: ["one", "two"] } };
    await correctMemory(structured, { ...values, content: structured.content }, "synthetic-csrf", signal);
    expect(fetch).toHaveBeenLastCalledWith(`/api/v1/memory/${id}`, expect.objectContaining({ method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": "synthetic-csrf" } }));
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ ...values, content: structured.content, expected_revision: 1 });
    await forgetMemory(entry, "synthetic-csrf", signal);
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ expected_revision: 1 });
  });
  it.each([401, 403, 404, 410, 422, 503])("does not expose upstream payload on status %s", async status => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private upstream text", { status })));
    await expect(readMemory(id, false, new AbortController().signal)).rejects.not.toThrow("private upstream text");
  });
  it("reports stale edits without retry or changing the revision", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("private", { status: 409 })); vi.stubGlobal("fetch", fetch);
    await expect(correctMemory(entry, values, "synthetic", new AbortController().signal)).rejects.toThrow("Discard your draft");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each([{ revision: "1" }, { scope: "work_private" }, { owner_id: "invalid" }, { content: [] }, { assessment: "auto" }, { expires_at: "invalid" }])("rejects malformed current entries %j", change => {
    expect(() => parseEntry({ ...entry, ...change })).toThrow("Invalid memory response");
  });
  it("drops payload from tombstones and rejects unbounded/invalid pages", () => {
    expect(parseEntry({ ...entry, state: "forgotten" })).not.toHaveProperty("content");
    expect(() => parsePage({ ...page, items: Array(51).fill(entry) })).toThrow();
    expect(() => parsePage({ ...page, next_cursor: "invalid" })).toThrow();
  });
  it("validates current-page export and historical snapshots as read-only", async () => {
    const snapshot = { ...entry } as Partial<ActiveMemory>; delete snapshot.expired; delete snapshot.eligible_for_context;
    const fetch = vi.fn().mockResolvedValueOnce(response(page)).mockResolvedValueOnce(response({ schema_version: 1, items: [{ revision: 1, actor_id: owner, created_at: entry.created_at, historical: false, eligible_for_context: false, snapshot }], next_cursor: null })); vi.stubGlobal("fetch", fetch);
    expect((await exportMemory(filters, new AbortController().signal)).items.length).toBe(1);
    expect(fetch.mock.calls[0][0]).toContain("/export?limit=25");
    expect((await historyMemory(id, 0, new AbortController().signal)).items[0].snapshot?.eligible_for_context).toBe(false);
  });
});
