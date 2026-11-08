import { afterEach, expect, it, vi } from "vitest";
import { parseDigest, prepareDigest } from "./discovery-digest-api";
import { emptyInboxFilters, searchProposals } from "./discovery-api";
import { fixture, owner, record } from "./test-support/discovery-digest";
afterEach(() => vi.unstubAllGlobals());
it("accepts explicit ordered snapshots and clones exact request selections", () => {
  const { payload, request } = fixture(), value = parseDigest(payload, request, owner); request.selections.reverse(); expect(value.request.selections[0].id).toBe(payload.bundle.items[0].id); expect(value.bundle.managed_copy).toBe(false);
});
it.each(["scope", "owner", "revision", "order", "duplicates", "empty", "size", "deadline", "retention", "flags", "purpose", "stage", "future", "source_date", "receipt"])("refuses inconsistent review %s", fault => {
  const { payload, request } = fixture();
  if (fault === "scope") payload.bundle.scope = "member_b_private";
  if (fault === "owner") payload.bundle.items[0].owner_id = payload.bundle.export_id;
  if (fault === "revision") payload.bundle.items[0].revision = 2;
  if (fault === "order") payload.bundle.items.reverse();
  if (fault === "duplicates") request.selections[1] = request.selections[0];
  if (fault === "empty") payload.bundle.items = [];
  if (fault === "size") payload.bundle_bytes = 65537;
  if (fault === "deadline") payload.valid_until = "2026-11-07T10:01:01Z";
  if (fault === "retention") payload.bundle.items[0].expires_at = "2026-11-07T10:00:30Z";
  if (fault === "flags") Object.assign(payload.bundle, { source_verification: true });
  if (fault === "purpose") payload.purpose = "download";
  if (fault === "stage") Object.assign(payload.bundle.items[0].content, { stage: "approved" });
  if (fault === "future") payload.bundle.items[0].updated_at = "2026-11-08T10:00:00Z";
  if (fault === "source_date") payload.bundle.items[0].content.evidence[0].observed_at = "2026-01-01T00:00:00";
  if (fault === "receipt") payload.review_id = "not-a-uuid";
  expect(() => parseDigest(payload, request, owner)).toThrow();
});
it("binds download acknowledgement, reviewed hash and receipt while allowing fresh export IDs", () => {
  const { payload, request } = fixture(); const copy = { ...request, purpose: "download" as const, acknowledge_copy_limits: true, review_id: payload.review_id, reviewed_hash: payload.reviewed_hash };
  payload.purpose = "download"; payload.bundle.export_id = "44444444-4444-4444-8444-444444444444";
  expect(parseDigest(payload, copy, owner).bundle.export_id).toBe(payload.bundle.export_id);
  for (const change of [{ acknowledge_copy_limits: false }, { review_id: payload.bundle.export_id }, { reviewed_hash: "b".repeat(64) }]) expect(() => parseDigest(payload, { ...copy, ...change }, owner)).toThrow();
});
it("uses bounded private inbox POST bodies, cursor/CSRF/no-store and no query in URL", async () => {
  const item = record(), fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ schema_version: 1, items: [item], next_cursor: null }))); vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal; await searchProposals({ ...emptyInboxFilters(), q: " private %_ query ", stage: "idea" }, true, { id: item.id, priority: 10 }, "synthetic", signal);
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/discovery/inbox"); expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ q: "private %_ query", topic: null, limit: 25, include_dismissed: true, after: item.id, after_priority: 10 }); expect(fetch.mock.calls[0][1]).toMatchObject({ method: "POST", signal, redirect: "error", cache: "no-store", credentials: "same-origin", headers: { "X-CSRF-Token": "synthetic" } });
});
it("posts only the chosen digest contract and does not retry/expose upstream refusal bodies", async () => {
  const { request } = fixture(), fetch = vi.fn().mockResolvedValue(new Response("private upstream", { status: 409 })); vi.stubGlobal("fetch", fetch);
  await expect(prepareDigest(request, { user: { id: owner, display_name: "Synthetic", scopes: [] }, csrfToken: "synthetic" }, new AbortController().signal)).rejects.toThrow("changed"); expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][0]).toBe("/api/v1/discovery/digest"); expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(request);
});
