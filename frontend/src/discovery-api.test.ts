import { afterEach, expect, it, vi } from "vitest";
import { createProposal, listProposals, parseProposal, readProposal, saveFeedback } from "./discovery-api";
import type { ProposalInput } from "./discovery-api";

const id = "11111111-1111-4111-8111-111111111111";
const input: ProposalInput = { scope: "member_a_private", title: "Synthetic proposal", topic: "synthetic", summary: "Synthetic summary", evidence: [{ title: "Source", url: "https://example.org/a", observed_at: "2026-01-01T00:00:00Z" }] };
const entry = { id, owner_id: "22222222-2222-4222-8222-222222222222", scope: "member_a_private", kind: "experience", state: "active", title: input.title, source_type: "manual", source_reference: "Synthetic", assessment: "tentative", revision: 1, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", expires_at: null, expired: false, eligible_for_context: true, priority: 0, action_authority: "interest_only", content: { record_type: "discovery_proposal", schema_version: 1, topic: input.topic, summary: input.summary, evidence: input.evidence, benefit: "Not assessed", privacy: "Not assessed", maturity_license: "Not assessed", hardware_cost: "Not assessed", alternatives_dependencies: "Not assessed", experiment: "Not proposed", feedback: null } };
const signal = () => new AbortController().signal;
const response = (v: unknown) => new Response(JSON.stringify(v));
afterEach(() => vi.unstubAllGlobals());
it("validates a private proposal and explicit interest score", () => {
  expect(parseProposal(entry).priority).toBe(0);
  expect(parseProposal({ ...entry, priority: 100, content: { ...entry.content, feedback: { choice: "very_interested", note: "Synthetic", recorded_at: entry.updated_at } } }).priority).toBe(100);
});
it.each([{ scope: "household_shared" }, { kind: "profile" }, { expired: true }, { action_authority: "approved" }, { priority: 100 }, { state: "forgotten" }])("rejects invalid proposal authority/state %j", change => {
  expect(() => parseProposal({ ...entry, ...change })).toThrow();
});
it.each([{ schema_version: 999 }, { record_type: "work" }, { topic: "invalid topic" }, { evidence: [] }, { privacy: "" }, { feedback: { choice: "approve_install", note: "", recorded_at: entry.updated_at } }])("rejects malformed envelope %j", change => {
  expect(() => parseProposal({ ...entry, content: { ...entry.content, ...change } })).toThrow();
});
it("uses bounded cursor queries with same-origin, no-store and cancellation", async () => {
  const fetch = vi.fn().mockResolvedValue(response({ schema_version: 1, items: [entry], next_cursor: null })); vi.stubGlobal("fetch", fetch);
  const abort = signal(); await listProposals(true, { id, priority: 0 }, abort);
  expect(fetch).toHaveBeenCalledWith(`/api/v1/discovery?limit=25&include_dismissed=true&after=${id}&after_priority=0`, expect.objectContaining({ cache: "no-store", redirect: "error", credentials: "same-origin", signal: abort }));
});
it("writes feedback/clear with displayed revision and CSRF", async () => {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(response(entry))); vi.stubGlobal("fetch", fetch);
  await createProposal(input, "synthetic", signal());
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(input);
  await saveFeedback(parseProposal(entry), "later", "Synthetic note", "synthetic", signal());
  expect(fetch.mock.calls[1][1].method).toBe("PUT");
  expect(fetch.mock.calls[1][1].headers["X-CSRF-Token"]).toBe("synthetic");
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ choice: "later", note: "Synthetic note", expected_revision: 1 });
  await saveFeedback(parseProposal(entry), null, "", "synthetic", signal());
  expect(JSON.parse(fetch.mock.calls[2][1].body).choice).toBeNull();
});
it("does not retry a revision conflict or expose upstream text", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("private failure", { status: 409 })); vi.stubGlobal("fetch", fetch);
  await expect(saveFeedback(parseProposal(entry), "later", "", "synthetic", signal())).rejects.not.toThrow("private failure");
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("rejects unbounded pages and invalid cursors", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(response({ schema_version: 1, items: Array(26).fill(entry), next_cursor: null })).mockResolvedValueOnce(response({ schema_version: 1, items: [], next_cursor: { id, priority: 999 } })); vi.stubGlobal("fetch", fetch);
  await expect(listProposals(false, null, signal())).rejects.toThrow();
  await expect(listProposals(false, null, signal())).rejects.toThrow();
});
it("propagates current read cancellation", async () => {
  const fetch = vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")); vi.stubGlobal("fetch", fetch);
  await expect(readProposal(id, signal())).rejects.toMatchObject({ name: "AbortError" });
});
