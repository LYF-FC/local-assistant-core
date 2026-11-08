export const memoryScopes = {
  household_shared: "Shared household", member_a_private: "Member A — private", member_b_private: "Member B — private",
  parents_child: "Parents — child", member_business: "Member B business", finance_private: "Finance — private",
} as const;
export const memoryKinds = { profile: "Profile", preference: "Preference", experience: "Experience", procedure: "Procedure", context: "Temporary context" } as const;
export type Scope = keyof typeof memoryScopes;
export type Kind = keyof typeof memoryKinds;
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type JsonObject = { [key: string]: Json };
export type Values = { title: string; content: JsonObject; source_type: "manual" | "document" | "conversation" | "feedback"; source_reference: string; assessment: "confirmed" | "tentative"; expires_at: string | null };
type Meta = { id: string; owner_id: string; scope: Scope; kind: Kind; revision: number; created_at: string; updated_at: string };
export type ActiveMemory = Meta & Values & { state: "active"; expired: boolean; eligible_for_context: boolean };
export type Entry = ActiveMemory | (Meta & { state: "forgotten" });
export type Filters = { scope: string; kind: string; expired: boolean; forgotten: boolean; after?: string };
export type Page = { schema_version: 1; generated_at: string; items: Entry[]; next_cursor: string | null };
export type History = { schema_version: 1; items: { revision: number; created_at: string; actor_id: string; historical: boolean; eligible_for_context: false; snapshot: ActiveMemory | null }[]; next_cursor: number | null };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const integer = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 1;
const date = (value: unknown): value is string => typeof value === "string" && Number.isFinite(Date.parse(value));
function invalid(): never { throw new Error("Invalid memory response"); }
function json(value: unknown, depth = 0): value is Json {
  if (depth > 8) return false;
  if (value === null || typeof value === "boolean" || typeof value === "string") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.length <= 256 && value.every(child => json(child, depth + 1));
  return object(value) && Object.keys(value).length <= 256 && Object.values(value).every(child => json(child, depth + 1));
}
export function parseEntry(value: unknown): Entry {
  if (!object(value) || typeof value.id !== "string" || !uuid.test(value.id) || typeof value.owner_id !== "string" || !uuid.test(value.owner_id) || typeof value.scope !== "string" || !Object.hasOwn(memoryScopes, value.scope) || typeof value.kind !== "string" || !Object.hasOwn(memoryKinds, value.kind) || !integer(value.revision) || !date(value.created_at) || !date(value.updated_at)) invalid();
  const meta: Meta = { id: value.id, owner_id: value.owner_id, scope: value.scope as Scope, kind: value.kind as Kind, revision: value.revision, created_at: value.created_at, updated_at: value.updated_at };
  if (value.state === "forgotten") return { ...meta, state: "forgotten" };
  if (value.state !== "active" || typeof value.title !== "string" || value.title.length > 160 || !object(value.content) || !json(value.content) || new TextEncoder().encode(JSON.stringify(value.content)).length > 32768 || typeof value.source_reference !== "string" || value.source_reference.length > 512 || !["manual", "document", "conversation", "feedback"].includes(value.source_type as string) || !["confirmed", "tentative"].includes(value.assessment as string) || !(value.expires_at === null || date(value.expires_at)) || typeof value.expired !== "boolean" || typeof value.eligible_for_context !== "boolean") invalid();
  return { ...meta, state: "active", title: value.title, content: value.content as JsonObject, source_type: value.source_type as Values["source_type"], source_reference: value.source_reference, assessment: value.assessment as Values["assessment"], expires_at: value.expires_at as string | null, expired: value.expired, eligible_for_context: value.eligible_for_context };
}
export function parsePage(value: unknown): Page {
  if (!object(value) || value.schema_version !== 1 || !date(value.generated_at) || !Array.isArray(value.items) || value.items.length > 50 || !(value.next_cursor === null || (typeof value.next_cursor === "string" && uuid.test(value.next_cursor)))) invalid();
  return { schema_version: 1, generated_at: value.generated_at, items: value.items.map(parseEntry), next_cursor: value.next_cursor as string | null };
}
export class MemoryError extends Error {
  constructor(public status: number) { super(status === 409 ? "This entry changed. Discard your draft and reload before saving." : status === 422 ? "Check the entry details, expiry and size." : [401, 403, 404, 410].includes(status) ? "Memory is no longer available. Refresh your session or list." : "Memory is unavailable. Try again."); }
}
async function request(path: string, signal: AbortSignal, method = "GET", body?: object, csrf?: string): Promise<unknown> {
  const response = await fetch(`/api/v1/memory${path}`, { method, signal, credentials: "same-origin", cache: "no-store", redirect: "error", headers: body ? { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? "" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) throw new MemoryError(response.status);
  return response.json();
}
function query(filters: Filters): string {
  const params = new URLSearchParams({ limit: "25" });
  if (filters.scope) params.set("scope", filters.scope);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.after) params.set("after", filters.after);
  if (filters.expired) params.set("include_expired", "true");
  if (filters.forgotten) params.set("include_forgotten", "true");
  return `?${params}`;
}
export async function listMemory(filters: Filters, signal: AbortSignal): Promise<Page> { return parsePage(await request(query(filters), signal)); }
export async function exportMemory(filters: Filters, signal: AbortSignal): Promise<Page> { return parsePage(await request(`/export${query(filters)}`, signal)); }
export async function readMemory(id: string, expired: boolean, signal: AbortSignal): Promise<Entry> { return parseEntry(await request(`/${id}?include_expired=${expired}`, signal)); }
export async function createMemory(values: Values, scope: Scope, kind: Kind, csrf: string, signal: AbortSignal): Promise<Entry> { return parseEntry(await request("", signal, "POST", { ...values, scope, kind }, csrf)); }
export async function correctMemory(entry: ActiveMemory, values: Values, csrf: string, signal: AbortSignal): Promise<Entry> { return parseEntry(await request(`/${entry.id}`, signal, "PATCH", { ...values, expected_revision: entry.revision }, csrf)); }
export async function forgetMemory(entry: ActiveMemory, csrf: string, signal: AbortSignal): Promise<Entry> { return parseEntry(await request(`/${entry.id}/forget`, signal, "POST", { expected_revision: entry.revision }, csrf)); }
export async function historyMemory(id: string, after: number, signal: AbortSignal): Promise<History> {
  const value = await request(`/${id}/history?limit=10&after=${after}`, signal);
  if (!object(value) || value.schema_version !== 1 || !Array.isArray(value.items) || value.items.length > 10 || !(value.next_cursor === null || integer(value.next_cursor))) invalid();
  const items: History["items"] = value.items.map(row => {
    if (!object(row) || !integer(row.revision) || !date(row.created_at) || typeof row.actor_id !== "string" || !uuid.test(row.actor_id) || typeof row.historical !== "boolean" || row.eligible_for_context !== false || !(row.snapshot === null || object(row.snapshot))) invalid();
    const snapshot = row.snapshot === null ? null : parseEntry({ ...row.snapshot as object, expired: false, eligible_for_context: false });
    if (snapshot?.state === "forgotten") invalid();
    return { revision: row.revision, created_at: row.created_at, actor_id: row.actor_id, historical: row.historical, eligible_for_context: false, snapshot };
  });
  return { schema_version: 1, items, next_cursor: value.next_cursor as number | null };
}
