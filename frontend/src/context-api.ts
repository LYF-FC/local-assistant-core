import { memoryKinds, memoryScopes, parseEntry } from "./memory-api";
import type { ActiveMemory, Scope } from "./memory-api";

export type Candidate = Pick<ActiveMemory, "id" | "scope" | "kind" | "revision" | "title" | "source_type" | "source_reference" | "expires_at">;
export type Selection = { id: string; expected_revision: number };
export type Candidates = { schema_version: 1; scope: Scope; items: Candidate[]; next_cursor: string | null };
export type Preview = { schema_version: 1; mode: "preview_only"; scope: Scope; model_invoked: false; execution_allowed: false; reference_only: true; generated_at: string; valid_until: string; items_bytes: number; max_bytes: number; items: ActiveMemory[] };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const kinds = ["profile", "preference", "procedure", "context"];
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const date = (v: unknown): v is string => typeof v === "string" && Number.isFinite(Date.parse(v));
const string = (v: unknown, max: number) => typeof v === "string" && v.trim().length > 0 && v.length <= max;
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 1;
function invalid(): never { throw new Error("Invalid context response"); }
export function parseCandidates(value: unknown, scope: Scope): Candidates {
  if (!object(value) || value.schema_version !== 1 || value.scope !== scope || !Object.hasOwn(memoryScopes, scope) || !Array.isArray(value.items) || value.items.length > 25 || !(value.next_cursor === null || (typeof value.next_cursor === "string" && uuid.test(value.next_cursor)))) invalid();
  const items = value.items.map(row => {
    if (!object(row) || typeof row.id !== "string" || !uuid.test(row.id) || row.scope !== scope || !kinds.includes(row.kind as string) || !Object.hasOwn(memoryKinds, row.kind as string) || !integer(row.revision) || !string(row.title, 160) || !string(row.source_reference, 512) || !["manual", "document", "conversation", "feedback"].includes(row.source_type as string) || !(row.expires_at === null || date(row.expires_at))) invalid();
    if (row.kind === "context" && row.expires_at === null) invalid();
    return { id: row.id, scope, kind: row.kind, revision: row.revision, title: row.title, source_type: row.source_type, source_reference: row.source_reference, expires_at: row.expires_at } as Candidate;
  });
  if (new Set(items.map(i => i.id)).size !== items.length || (value.next_cursor !== null && value.next_cursor !== items.at(-1)?.id)) invalid();
  return { schema_version: 1, scope, items, next_cursor: value.next_cursor as string | null };
}
export function parsePreview(value: unknown, scope: Scope, selections: Selection[], maxBytes: number): Preview {
  if (!object(value) || value.schema_version !== 1 || value.mode !== "preview_only" || value.scope !== scope || value.model_invoked !== false || value.execution_allowed !== false || value.reference_only !== true || !date(value.generated_at) || !date(value.valid_until) || !integer(value.items_bytes) || value.max_bytes !== maxBytes || maxBytes < 512 || maxBytes > 16384 || value.items_bytes > maxBytes || !Array.isArray(value.items) || value.items.length !== selections.length || selections.length < 1 || selections.length > 10 || new Set(selections.map(i => i.id)).size !== selections.length) invalid();
  const generated = Date.parse(value.generated_at); const until = Date.parse(value.valid_until);
  if (until <= Date.now() || until <= generated || until - generated > 60000 || generated > Date.now() + 5000) invalid();
  const items = value.items.map((raw, index) => {
    const entry = parseEntry(raw);
    if (entry.state !== "active" || entry.scope !== scope || entry.id !== selections[index].id || entry.revision !== selections[index].expected_revision || entry.assessment !== "confirmed" || entry.expired || !entry.eligible_for_context || !kinds.includes(entry.kind) || "record_type" in entry.content || (entry.expires_at !== null && until > Date.parse(entry.expires_at)) || (entry.kind === "context" && entry.expires_at === null)) invalid();
    return entry;
  });
  return { schema_version: 1, mode: "preview_only", scope, model_invoked: false, execution_allowed: false, reference_only: true, generated_at: value.generated_at, valid_until: value.valid_until, items_bytes: value.items_bytes, max_bytes: maxBytes, items };
}
export class ContextError extends Error {
  constructor(public status: number) { super(status === 409 ? "Selected records changed. Refresh the candidates and choose again." : status === 413 ? "The selection exceeds the byte budget. Choose fewer entries or a larger budget." : [401, 403, 404, 410].includes(status) ? "Context is no longer available. Refresh the candidates." : status === 422 ? "Context request or saved records are invalid. Inspect entries in Memory." : "Context is unavailable. Try again."); }
}
async function request(path: string, signal: AbortSignal, body?: object, csrf?: string) {
  const response = await fetch(`/api/v1/context/${path}`, { method: body ? "POST" : "GET", signal, credentials: "same-origin", cache: "no-store", redirect: "error", headers: body ? { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? "" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) throw new ContextError(response.status);
  return response.json();
}
export async function listCandidates(scope: Scope, after: string | undefined, signal: AbortSignal) {
  const query = new URLSearchParams({ scope, limit: "25" }); if (after) query.set("after", after);
  return parseCandidates(await request(`candidates?${query}`, signal), scope);
}
export async function buildPreview(scope: Scope, selections: Selection[], maxBytes: number, csrf: string, signal: AbortSignal) {
  return parsePreview(await request("preview", signal, { scope, selections, max_bytes: maxBytes }, csrf), scope, selections, maxBytes);
}
