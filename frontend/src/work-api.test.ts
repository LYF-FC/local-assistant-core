import { afterEach, expect, it, vi } from "vitest";
import { listWorkspaces, parseWorkPage, parseWorkStatus, workStatus } from "./work-api";
const id = "11111111-1111-4111-8111-111111111111";
const item = { id, slug: "synthetic-team-a" };
const page = { schema_version: 1, capability: "work_private", items: [item], next_cursor: null };
const status = { schema_version: 1, workspace: item, capability: "work_private", mode: "access_foundation_only", authority_mode: "transaction_snapshot", checked_at: "2026-01-01T12:00:00Z", ingestion_allowed: false, model_invoked: false, execution_allowed: false, pending_gates: ["a", "b", "c", "d", "e"] };
const signal = () => new AbortController().signal;
afterEach(() => vi.unstubAllGlobals());
it("validates explicit work metadata and disabled runtime", () => {
  expect(parseWorkPage(page).items).toEqual([item]);
  expect(parseWorkStatus(status, id).workspace).toEqual(item);
});
it.each([{ capability: "member_a_private" }, { items: [item, item] }, { items: Array(26).fill(item) }, { next_cursor: "bad" }, { next_cursor: "22222222-2222-4222-8222-222222222222" }, { items: [{ ...item, slug: "real-employer" }] }])("rejects invalid registry %j", change => {
  expect(() => parseWorkPage({ ...page, ...change })).toThrow();
});
it.each([{ ingestion_allowed: true }, { model_invoked: true }, { execution_allowed: true }, { mode: "ready" }, { authority_mode: "reusable_token" }, { checked_at: "invalid" }, { capability: "technical_admin" }, { workspace: { ...item, id: "22222222-2222-4222-8222-222222222222" } }, { pending_gates: [] }])("rejects unsafe/different workspace status %j", change => {
  expect(() => parseWorkStatus({ ...status, ...change }, id)).toThrow();
});
it("uses read-only no-store same-origin requests with cancellation", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(page))).mockResolvedValueOnce(new Response(JSON.stringify(status))); vi.stubGlobal("fetch", fetch);
  const abort = signal();
  await listWorkspaces(id, abort); await workStatus(id, abort);
  expect(fetch).toHaveBeenNthCalledWith(1, `/api/v1/work/workspaces?limit=25&after=${id}`, expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error", signal: abort }));
  expect(fetch).toHaveBeenNthCalledWith(2, `/api/v1/work/workspaces/${id}/status`, expect.objectContaining({ signal: abort }));
});
it.each([401, 403, 404, 503])("sanitizes errors without retry %s", async code => {
  const fetch = vi.fn().mockResolvedValue(new Response("private upstream data", { status: code })); vi.stubGlobal("fetch", fetch);
  await expect(listWorkspaces(null, signal())).rejects.not.toThrow("private upstream data");
  expect(fetch).toHaveBeenCalledTimes(1);
});
