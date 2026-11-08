import { afterEach, expect, it, vi } from "vitest";
import { createIdea, isIdea, parseProposal, saveProposalDetails } from "./discovery-api";
const at = "2026-01-01T00:00:00Z", id = "11111111-1111-4111-8111-111111111111";
const idea = { id, owner_id: id, scope: "member_a_private", kind: "experience", state: "active", revision: 1, title: "Synthetic idea", source_type: "manual", source_reference: "Manually entered Discovery idea; no evidence supplied", assessment: "tentative", expires_at: null, expired: false, eligible_for_context: false, created_at: at, updated_at: at, priority: 0, action_authority: "interest_only", content: { record_type: "discovery_proposal", schema_version: 2, stage: "idea", topic: "unclassified", summary: "Unknown", evidence: [], benefit: "Not assessed", privacy: "Not assessed", maturity_license: "Not assessed", hardware_cost: "Not assessed", alternatives_dependencies: "Not assessed", experiment: "Not proposed", feedback: null } };
afterEach(() => vi.unstubAllGlobals());
it("accepts explicit evidence-free v2 ideas without elevating assessment or authority", () => { const value = parseProposal(idea); expect(isIdea(value)).toBe(true); expect(value.content.evidence).toEqual([]); expect(value.assessment).toBe("tentative"); });
it("accepts v2 evidenced proposals alongside existing v1", () => {
  const content = { ...idea.content, stage: "proposal", evidence: [{ title: "Synthetic", url: "https://example.org/a", observed_at: at }] };
  expect(isIdea(parseProposal({ ...idea, content }))).toBe(false);
  const { stage: _stage, ...legacy } = content; expect(parseProposal({ ...idea, content: { ...legacy, schema_version: 1 } }).content.schema_version).toBe(1);
});
it.each([ { schema_version: 2, stage: undefined }, { stage: "approved" }, { stage: "proposal" }, { stage: "idea", evidence: [{ title: "Synthetic", url: "https://example.org/a", observed_at: at }] }, { schema_version: 1 }, { schema_version: 99 } ])("rejects mixed/unknown stages %j", change => { expect(() => parseProposal({ ...idea, content: { ...idea.content, ...change } })).toThrow(); });
it("writes only deliberate idea fields and exact-revision details with CSRF/cancellation", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(idea))); vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal, input = { scope: "member_a_private" as const, title: "Synthetic", summary: "Unknown" };
  await createIdea(input, "synthetic-csrf", signal); expect(fetch.mock.calls[0][0]).toBe("/api/v1/discovery/ideas"); expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(input);
  fetch.mockResolvedValue(new Response(JSON.stringify(idea)));
  const body = { title: "Synthetic", topic: "sample", summary: "Unknown", evidence: [{ title: "Synthetic", url: "https://example.org/a", observed_at: at }] };
  await saveProposalDetails(parseProposal(idea), body, "synthetic-csrf", signal);
  expect(fetch.mock.calls[1][0]).toBe(`/api/v1/discovery/${id}/details`); expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ ...body, expected_revision: 1 }); expect(fetch.mock.calls[1][1]).toMatchObject({ method: "PUT", signal, credentials: "same-origin", cache: "no-store", redirect: "error", headers: { "X-CSRF-Token": "synthetic-csrf" } });
});
it("propagates a details conflict once without exposing upstream content", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("private upstream", { status: 409 })); vi.stubGlobal("fetch", fetch);
  await expect(saveProposalDetails(parseProposal(idea), { title: "Synthetic", topic: "sample", summary: "Unknown", evidence: [] }, "synthetic", new AbortController().signal)).rejects.toThrow("changed"); expect(fetch).toHaveBeenCalledTimes(1);
});
