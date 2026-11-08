import { afterEach, expect, it, vi } from "vitest";
import { buildPreview, listCandidates, parseCandidates, parsePreview } from "./context-api";
import type { Selection } from "./context-api";

const id = "11111111-1111-4111-8111-111111111111";
const candidate = { id, scope: "member_a_private", kind: "preference", title: "Synthetic current preference", revision: 1, source_type: "manual", source_reference: "Synthetic explicit source", expires_at: null };
const entry = { ...candidate, owner_id: "22222222-2222-4222-8222-222222222222", state: "active", assessment: "confirmed", content: { text: "Synthetic context" }, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", expired: false, eligible_for_context: true };
const selections: Selection[] = [{ id, expected_revision: 1 }];
const bundle = () => ({ schema_version: 1, mode: "preview_only", scope: "member_a_private", model_invoked: false, execution_allowed: false, reference_only: true, generated_at: new Date().toISOString(), valid_until: new Date(Date.now() + 30000).toISOString(), items_bytes: 700, max_bytes: 8192, items: [entry] });
const catalogue = { schema_version: 1, scope: "member_a_private", items: [candidate], next_cursor: null };
const signal = () => new AbortController().signal;
const response = (v: unknown) => new Response(JSON.stringify(v));
afterEach(() => vi.unstubAllGlobals());
it("keeps metadata-only candidates and validates selected provenance", () => {
  expect(parseCandidates(catalogue, "member_a_private").items[0]).toEqual(candidate);
  expect(parsePreview(bundle(), "member_a_private", selections, 8192).items[0]).toEqual(entry);
});
it.each([{ items: Array(26).fill(candidate) }, { scope: "household_shared" }, { next_cursor: "invalid" }, { items: [candidate, candidate] }])("rejects unsafe catalogue %j", change => {
  expect(() => parseCandidates({ ...catalogue, ...change }, "member_a_private")).toThrow();
});
it.each([{ model_invoked: true }, { execution_allowed: true }, { reference_only: false }, { items_bytes: 8193 }, { max_bytes: 16384 }, { valid_until: "2020-01-01T00:00:00Z" }])("rejects unsafe preview authority/bounds %j", change => {
  expect(() => parsePreview({ ...bundle(), ...change }, "member_a_private", selections, 8192)).toThrow();
});
it.each([{ scope: "household_shared" }, { assessment: "tentative" }, { kind: "experience" }, { content: { record_type: null } }, { revision: 2 }, { expired: true }])("rejects ineligible or different selected entry %j", change => {
  expect(() => parsePreview({ ...bundle(), items: [{ ...entry, ...change }] }, "member_a_private", selections, 8192)).toThrow();
});
it("rejects future clocks/overlong lifetimes and source-expiry overrun", () => {
  const b = bundle();
  expect(() => parsePreview({ ...b, generated_at: new Date(Date.now() + 60000).toISOString(), valid_until: new Date(Date.now() + 90000).toISOString() }, "member_a_private", selections, 8192)).toThrow();
  expect(() => parsePreview({ ...b, valid_until: new Date(Date.now() + 120000).toISOString() }, "member_a_private", selections, 8192)).toThrow();
  expect(() => parsePreview({ ...b, items: [{ ...entry, expires_at: new Date(Date.now() + 1000).toISOString() }] }, "member_a_private", selections, 8192)).toThrow();
});
it("uses bounded explicit scope/cursor reads with cancellation", async () => {
  const fetch = vi.fn().mockResolvedValue(response(catalogue)); vi.stubGlobal("fetch", fetch); const abort = signal();
  await listCandidates("member_a_private", id, abort);
  expect(fetch).toHaveBeenCalledWith(`/api/v1/context/candidates?scope=member_a_private&limit=25&after=${id}`, expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error", signal: abort }));
});
it("sends only selected IDs/revisions/scope/budget with CSRF", async () => {
  const fetch = vi.fn().mockResolvedValue(response(bundle())); vi.stubGlobal("fetch", fetch);
  await buildPreview("member_a_private", selections, 8192, "synthetic-csrf", signal());
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ scope: "member_a_private", selections, max_bytes: 8192 });
  expect(fetch.mock.calls[0][1].headers["X-CSRF-Token"]).toBe("synthetic-csrf");
});
it.each([401, 403, 404, 409, 413, 422, 503])("sanitizes upstream error %s without retry", async status => {
  const fetch = vi.fn().mockResolvedValue(new Response("private upstream context", { status })); vi.stubGlobal("fetch", fetch);
  await expect(buildPreview("member_a_private", selections, 8192, "synthetic", signal())).rejects.not.toThrow("private upstream context");
  expect(fetch).toHaveBeenCalledTimes(1);
});
