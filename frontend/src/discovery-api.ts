import { MemoryError, parseEntry } from "./memory-api";
import type { ActiveMemory } from "./memory-api";

export const choices = { very_interested: "Very interested — investigate further", later: "Interested — later", covered: "Already covered", not_relevant: "Not relevant" } as const;
export type Choice = keyof typeof choices;
export type ProposalInput = { scope: "member_a_private" | "member_b_private"; title: string; topic: string; summary: string; evidence: { title: string; url: string; observed_at: string }[]; benefit?: string; privacy?: string; maturity_license?: string; hardware_cost?: string; alternatives_dependencies?: string; experiment?: string };
export type Proposal = ActiveMemory & { priority: number; action_authority: "interest_only"; content: { record_type: "discovery_proposal"; schema_version: 1 | 2; stage?: "idea" | "proposal"; topic: string; summary: string; evidence: ProposalInput["evidence"]; benefit: string; privacy: string; maturity_license: string; hardware_cost: string; alternatives_dependencies: string; experiment: string; feedback: { choice: Choice | null; note: string; recorded_at: string } | null } };
export type Cursor = { id: string; priority: number };
export type Proposals = { schema_version: 1; items: Proposal[]; next_cursor: Cursor | null };
const scores = { very_interested: 100, later: 10, covered: -10, not_relevant: -20 };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const obj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const date = (v: unknown) => typeof v === "string" && Number.isFinite(Date.parse(v));
const bounded = (v: unknown, n: number) => typeof v === "string" && v.length > 0 && v.length <= n;
function invalid(): never { throw new Error("Invalid Discovery response"); }
export function parseProposal(value: unknown): Proposal {
  const entry = parseEntry(value);
  if (!obj(value) || entry.state !== "active" || entry.kind !== "experience" || !["member_a_private", "member_b_private"].includes(entry.scope) || entry.expired || value.action_authority !== "interest_only") invalid();
  const c = entry.content;
  if (c.record_type !== "discovery_proposal" || !(c.schema_version === 1 || c.schema_version === 2) || !bounded(c.topic, 64) || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(c.topic as string) || !bounded(c.summary, 1000) || !Array.isArray(c.evidence) || c.evidence.length > 5) invalid();
  const idea = c.schema_version === 2 && c.stage === "idea";
  if ((c.schema_version === 1 && Object.hasOwn(c, "stage")) || (c.schema_version === 2 && c.stage !== "idea" && c.stage !== "proposal") || (idea ? c.evidence.length !== 0 : c.evidence.length < 1)) invalid();
  for (const item of c.evidence) {
    if (!obj(item) || !bounded(item.title, 160) || !bounded(item.url, 512) || !(item.url as string).startsWith("https://") || !date(item.observed_at)) invalid();
  }
  for (const field of ["benefit", "privacy", "maturity_license", "hardware_cost", "alternatives_dependencies"]) if (!bounded(c[field], 512)) invalid();
  if (!bounded(c.experiment, 1000)) invalid();
  let priority = 0;
  if (c.feedback !== null) {
    const f = c.feedback;
    if (!obj(f) || !(f.choice === null || (typeof f.choice === "string" && Object.hasOwn(choices, f.choice))) || typeof f.note !== "string" || f.note.length > 500 || !date(f.recorded_at)) invalid();
    priority = f.choice === null ? 0 : scores[f.choice as Choice];
  }
  if (value.priority !== priority) invalid();
  return { ...entry, priority, action_authority: "interest_only" } as Proposal;
}
async function request(path: string, signal: AbortSignal, method = "GET", body?: object, csrf?: string) {
  const result = await fetch(`/api/v1/discovery${path}`, { method, signal, cache: "no-store", credentials: "same-origin", redirect: "error", headers: body ? { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? "" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!result.ok) throw new MemoryError(result.status);
  return result.json();
}
export async function listProposals(dismissed: boolean, after: Cursor | null, signal: AbortSignal): Promise<Proposals> {
  const query = new URLSearchParams({ limit: "25", include_dismissed: String(dismissed) });
  if (after) { query.set("after", after.id); query.set("after_priority", String(after.priority)); }
  const value: unknown = await request(`?${query}`, signal);
  if (!obj(value) || value.schema_version !== 1 || !Array.isArray(value.items) || value.items.length > 25) invalid();
  const cursor = value.next_cursor;
  if (!(cursor === null || (obj(cursor) && typeof cursor.id === "string" && uuid.test(cursor.id) && [100, 10, 0, -10, -20].includes(cursor.priority as number)))) invalid();
  return { schema_version: 1, items: value.items.map(parseProposal), next_cursor: cursor as Cursor | null };
}
export async function readProposal(id: string, signal: AbortSignal) { return parseProposal(await request(`/${id}`, signal)); }
export async function createProposal(body: ProposalInput, csrf: string, signal: AbortSignal) { return parseProposal(await request("", signal, "POST", body, csrf)); }
export async function saveFeedback(entry: Proposal, choice: Choice | null, note: string, csrf: string, signal: AbortSignal) { return parseProposal(await request(`/${entry.id}/feedback`, signal, "PUT", { expected_revision: entry.revision, choice, note }, csrf)); }

export type IdeaInput = { scope: ProposalInput["scope"]; title: string; summary: string; topic?: string };
export const isIdea = (entry: Proposal) => entry.content.schema_version === 2 && entry.content.stage === "idea";
export async function createIdea(body: IdeaInput, csrf: string, signal: AbortSignal) { return parseProposal(await request("/ideas", signal, "POST", body, csrf)); }
export async function saveProposalDetails(entry: Proposal, body: Omit<ProposalInput, "scope">, csrf: string, signal: AbortSignal) { return parseProposal(await request(`/${entry.id}/details`, signal, "PUT", { ...body, expected_revision: entry.revision }, csrf)); }

export type InboxFilters = { q: string; topic: string; stage: "all" | "idea" | "proposal"; interest: "all" | "unanswered" | Choice };
export const emptyInboxFilters = (): InboxFilters => ({ q: "", topic: "", stage: "all", interest: "all" });
export async function searchProposals(filters: InboxFilters, dismissed: boolean, after: Cursor | null, csrf: string, signal: AbortSignal): Promise<Proposals> {
  const value: unknown = await request("/inbox", signal, "POST", { ...filters, q: filters.q.trim(), topic: filters.topic.trim() || null, limit: 25, include_dismissed: dismissed, after: after?.id ?? null, after_priority: after?.priority ?? null }, csrf);
  if (!obj(value) || value.schema_version !== 1 || !Array.isArray(value.items) || value.items.length > 25) invalid();
  const cursor = value.next_cursor;
  if (!(cursor === null || (obj(cursor) && typeof cursor.id === "string" && uuid.test(cursor.id) && [100, 10, 0, -10, -20].includes(cursor.priority as number)))) invalid();
  const items = value.items.map(parseProposal);
  if (new Set(items.map(item => item.id)).size !== items.length || (cursor !== null && (!items.length || (cursor as Cursor).id !== items.at(-1)!.id || (cursor as Cursor).priority !== items.at(-1)!.priority))) invalid();
  return { schema_version: 1, items, next_cursor: cursor as Cursor | null };
}
