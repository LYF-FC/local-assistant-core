import type { Session } from "./api";
import { parseProposal } from "./discovery-api";
import type { Proposal, ProposalInput } from "./discovery-api";
import { MemoryError } from "./memory-api";

export type DigestSelection = { id: string; expected_revision: number };
export type DigestRequest = { scope: ProposalInput["scope"]; selections: DigestSelection[]; purpose: "preview" | "download"; review_id?: string; reviewed_hash?: string; acknowledge_copy_limits?: boolean };
export type DigestBundle = { schema_version: 1; mode: "selected_discovery_digest"; scope: ProposalInput["scope"]; export_id: string; prepared_at: string; retain_until: string | null; managed_copy: false; source_verification: false; execution_allowed: false; items: Proposal[] };
export type DigestReview = { schema_version: 1; mode: "discovery_digest_review"; checked_at: string; valid_until: string; purpose: "preview" | "download"; review_id: string; reviewed_hash: string; bundle_bytes: number; bundle: DigestBundle; request: DigestRequest };
export class DigestError extends Error {}
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
function fail(): never { throw new DigestError("The Discovery digest response could not be verified. Prepare a fresh review."); }
const instant = (v: unknown): v is string => typeof v === "string" && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
export function parseDigest(v: unknown, request: DigestRequest, owner: string): DigestReview {
  if (!object(v) || !object(v.bundle)) return fail();
  const b = v.bundle;
  if (v.schema_version !== 1 || v.mode !== "discovery_digest_review" || v.purpose !== request.purpose || !instant(v.checked_at) || !instant(v.valid_until) || Date.parse(v.valid_until) <= Date.parse(v.checked_at) || Date.parse(v.valid_until) - Date.parse(v.checked_at) > 60000 || typeof v.review_id !== "string" || !uuid.test(v.review_id) || typeof v.reviewed_hash !== "string" || !/^[a-f0-9]{64}$/.test(v.reviewed_hash) || !Number.isSafeInteger(v.bundle_bytes) || (v.bundle_bytes as number) < 1 || (v.bundle_bytes as number) > 65536) return fail();
  if (b.schema_version !== 1 || b.mode !== "selected_discovery_digest" || b.scope !== request.scope || !["member_a_private", "member_b_private"].includes(String(b.scope)) || typeof b.export_id !== "string" || !uuid.test(b.export_id) || !instant(b.prepared_at) || Date.parse(b.prepared_at) !== Date.parse(v.checked_at) || b.managed_copy !== false || b.source_verification !== false || b.execution_allowed !== false || !(b.retain_until === null || (instant(b.retain_until) && Date.parse(b.retain_until) >= Date.parse(v.valid_until))) || !Array.isArray(b.items) || b.items.length < 1 || b.items.length > 10 || b.items.length !== request.selections.length || new Set(request.selections.map(s => s.id)).size !== request.selections.length) return fail();
  if (request.purpose === "download" && (request.acknowledge_copy_limits !== true || v.review_id !== request.review_id || v.reviewed_hash !== request.reviewed_hash)) return fail();
  const items = b.items.map((raw, index) => {
    const item = parseProposal(raw), selected = request.selections[index];
    if (!instant(item.created_at) || !instant(item.updated_at) || (item.expires_at !== null && !instant(item.expires_at)) || !item.content.evidence.every(source => instant(source.observed_at) && Date.parse(source.observed_at) <= Date.parse(v.checked_at as string) + 300000)) return fail();
    if (item.id !== selected.id || item.revision !== selected.expected_revision || item.scope !== request.scope || item.owner_id !== owner || Date.parse(item.created_at) > Date.parse(item.updated_at) || Date.parse(item.updated_at) > Date.parse(v.checked_at as string) || (item.expires_at !== null && Date.parse(item.expires_at) < Date.parse(v.valid_until as string))) return fail();
    return item;
  });
  const earliest = items.map(item => item.expires_at).filter((at): at is string => at !== null).sort((a, c) => Date.parse(a) - Date.parse(c))[0] ?? null;
  if ((earliest === null) !== (b.retain_until === null) || (earliest !== null && Date.parse(earliest) !== Date.parse(b.retain_until as string))) return fail();
  if (new TextEncoder().encode(JSON.stringify(b)).length > 65536) return fail();
  return { schema_version: 1, mode: "discovery_digest_review", checked_at: v.checked_at, valid_until: v.valid_until, purpose: request.purpose, review_id: v.review_id, reviewed_hash: v.reviewed_hash, bundle_bytes: v.bundle_bytes as number, bundle: { schema_version: 1, mode: "selected_discovery_digest", scope: request.scope, export_id: b.export_id, prepared_at: b.prepared_at, retain_until: b.retain_until as string | null, managed_copy: false, source_verification: false, execution_allowed: false, items }, request: { ...request, selections: request.selections.map(s => ({ ...s })) } };
}
export async function prepareDigest(request: DigestRequest, session: Session, signal: AbortSignal): Promise<DigestReview> {
  const response = await fetch("/api/v1/discovery/digest", { method: "POST", signal, credentials: "same-origin", cache: "no-store", redirect: "error", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrfToken }, body: JSON.stringify(request) });
  if (!response.ok) throw new MemoryError(response.status);
  return parseDigest(await response.json(), request, session.user.id);
}
