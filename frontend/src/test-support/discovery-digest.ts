import type { Proposal } from "../discovery-api";
import type { DigestRequest } from "../discovery-digest-api";
export const owner = "11111111-1111-4111-8111-111111111111";
export function record(n = 1, idea = false): Proposal {
  return { id: `a0000000-0000-4000-8000-${String(n).padStart(12, "0")}`, owner_id: owner, scope: "member_a_private", kind: "experience", state: "active", revision: 1, title: `Synthetic Discovery ${n}`, source_type: "manual", source_reference: "Synthetic manually reported source", assessment: "tentative", expires_at: null, expired: false, eligible_for_context: true, created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-02T10:00:00Z", priority: 0, action_authority: "interest_only", content: { record_type: "discovery_proposal", schema_version: 2, stage: idea ? "idea" : "proposal", topic: "synthetic-review", summary: "Synthetic summary with _literal_ text", evidence: idea ? [] : [{ title: "Synthetic primary source", url: "https://example.org/a_(source)", observed_at: "2026-01-01T00:00:00Z" }], benefit: "Not assessed", privacy: "Not assessed", maturity_license: "Not assessed", hardware_cost: "Not assessed", alternatives_dependencies: "Not assessed", experiment: "Not proposed", feedback: null } };
}
export function fixture(items = [record(1), record(2, true)]) {
  const request: DigestRequest = { scope: "member_a_private", purpose: "preview", selections: items.map(item => ({ id: item.id, expected_revision: item.revision })) };
  const bundle = { schema_version: 1, mode: "selected_discovery_digest", scope: "member_a_private", export_id: "22222222-2222-4222-8222-222222222222", prepared_at: "2026-11-07T10:00:00Z", retain_until: null, managed_copy: false, source_verification: false, execution_allowed: false, items };
  return { request, payload: { schema_version: 1, mode: "discovery_digest_review", checked_at: "2026-11-07T10:00:00Z", valid_until: "2026-11-07T10:01:00Z", purpose: "preview", review_id: "33333333-3333-4333-8333-333333333333", reviewed_hash: "a".repeat(64), bundle_bytes: new TextEncoder().encode(JSON.stringify(bundle)).length, bundle } };
}
