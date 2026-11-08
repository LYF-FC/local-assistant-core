import type { Session } from "./api";

export type Operation = "capture_draft" | "correct_note" | "forget_note" | "confirm_note";
export type Section = "notes" | "sources" | "parties" | "policies" | "requests";
export type Choice = { id: string; label: string };
export type Policy = { id: string; max_age_seconds: number };
export type NoteRow = { id: string; revision: number; state: "draft" | "confirmed" | "forgotten"; label: string | null; content_available: boolean; retain_until: string | null };
export type RequestRow = { id: string; operation: Operation; request_id: string; target_record_id: string | null; expected_revision: number | null; state: "pending" | "applied" | "denied"; record_id: string | null; revision: number | null; expires_at: string; prepared_at: string; within_lifetime: boolean };
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Pages = { notes?: Page<NoteRow>; sources?: Page<Choice>; parties?: Page<Choice>; policies?: Page<Policy>; requests?: Page<RequestRow> & { pending_count: number } };
export type Features = { capture: boolean; review: boolean; confirmation: boolean; changes: boolean; export: boolean };
export type Frame = { workspace_id: string; checked_at: string; valid_until: string; features: Features };
export type Catalogue = Frame & { pages: Pages };
export type Draft = { kind: "observation" | "question" | "decision" | "action"; marker: string; source_ids: string[]; owner_id: string | null; due_at: string | null; retain_until: string };
export type Note = Draft & { id: string; workspace_id: string; policy_id: string; revision: number; state: "draft" | "confirmed"; actor_id: string; created_at: string; updated_at: string };
export type Inspection = Frame & { item: Note; payload_hash: string; references: { sources: Choice[]; owner: { id: string; label: string | null; available: boolean } | null; policy: Policy } };
export type Action = { operation: Operation; request_id: string; target_record_id: string | null; expected_revision: number | null; body: Record<string, unknown>; review?: { body: Record<string, unknown>; receipt?: string } };
export type Ack = { id: string; state: "pending" | "applied" | "denied"; record_id: string | null; revision: number | null; expires_at: string };
export class NotesError extends Error {
  constructor(public status: number) { super(status === 401 ? "Sign in again to use Work notes." : status === 409 ? "This version or request has changed. Reload and check its status." : status === 413 ? "The selected export is too large. Choose fewer notes." : status === 422 ? "Check the sample note and selected options." : "Synthetic Work notes are unavailable. Reload current access."); }
}
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const operations = ["capture_draft", "correct_note", "forget_note", "confirm_note"] as const;
function fail(): never { throw new Error("Invalid synthetic notes response"); }
function obj(v: unknown): Record<string, unknown> { if (!v || typeof v !== "object" || Array.isArray(v)) return fail(); return v as Record<string, unknown>; }
function id(v: unknown): string { if (typeof v !== "string" || !uuidPattern.test(v)) return fail(); return v.toLowerCase(); }
function date(v: unknown): string { if (typeof v !== "string" || !Number.isFinite(Date.parse(v))) return fail(); return v; }
function integer(v: unknown, min: number, max: number): number { if (!Number.isSafeInteger(v) || (v as number) < min || (v as number) > max) return fail(); return v as number; }
function bool(v: unknown): boolean { if (typeof v !== "boolean") return fail(); return v; }
function label(v: unknown): string { if (typeof v !== "string" || !/^[a-zA-Z0-9 _.-]{1,246}$/.test(v)) return fail(); return v; }
function choice(v: unknown): Choice { const x = obj(v); return { id: id(x.id), label: label(x.label) }; }
function policy(v: unknown): Policy { const x = obj(v); return { id: id(x.id), max_age_seconds: integer(x.max_age_seconds, 1, 31536000) }; }
function frame(v: unknown, workspace: string, mode: string): [Record<string, unknown>, Frame] {
  const x = obj(v), flags = obj(x.features);
  const checked = date(x.checked_at), until = date(x.valid_until);
  if (x.schema_version !== 1 || x.mode !== mode || id(x.workspace_id) !== workspace || x.model_invoked !== false || x.execution_allowed !== false || x.real_ingestion_allowed !== false || Date.parse(until) <= Date.parse(checked) || Date.parse(until) - Date.parse(checked) > 60000) return fail();
  return [x, { workspace_id: workspace, checked_at: checked, valid_until: until, features: { capture: bool(flags.capture), review: bool(flags.review), confirmation: bool(flags.confirmation), changes: bool(flags.changes), export: bool(flags.export) } }];
}
function noteRow(v: unknown): NoteRow {
  const x = obj(v); if (!["draft", "confirmed", "forgotten"].includes(String(x.state))) return fail();
  const available = bool(x.content_available), text = x.label === null ? null : label(x.label);
  if (available !== (text !== null) || (x.state === "forgotten" && available)) return fail();
  return { id: id(x.id), revision: integer(x.revision, 1, 101), state: x.state as NoteRow["state"], label: text, content_available: available, retain_until: x.retain_until === null ? null : date(x.retain_until) };
}
export function parseRequest(v: unknown): RequestRow {
  const x = obj(v); if (!operations.includes(x.operation as Operation) || !["pending", "applied", "denied"].includes(String(x.state))) return fail();
  const op = x.operation as Operation, target = x.target_record_id === null ? null : id(x.target_record_id), expected = x.expected_revision === null ? null : integer(x.expected_revision, 1, 100);
  const record = x.record_id === null ? null : id(x.record_id), revision = x.revision === null ? null : integer(x.revision, 1, 101);
  if ((op === "capture_draft") !== (target === null && expected === null) || (op !== "capture_draft" && (!target || expected === null)) || (x.state === "applied" ? (!record || revision !== (op === "capture_draft" ? 1 : expected! + 1) || (target !== null && record !== target)) : (record !== null || revision !== null))) return fail();
  return { id: id(x.id), operation: op, request_id: id(x.request_id), target_record_id: target, expected_revision: expected, state: x.state as RequestRow["state"], record_id: record, revision, expires_at: date(x.expires_at), prepared_at: date(x.prepared_at), within_lifetime: bool(x.within_lifetime) };
}
function page<T extends { id: string }>(v: unknown, parse: (v: unknown) => T): Page<T> {
  const x = obj(v); if (!Array.isArray(x.items) || x.items.length > 25) return fail();
  const items = x.items.map(parse), next = x.next_cursor === null ? null : id(x.next_cursor);
  if (new Set(items.map(item => item.id)).size !== items.length || (next !== null && next !== items.at(-1)?.id)) return fail();
  return { items, next_cursor: next };
}
export function parseCatalogue(v: unknown, workspace: string, expected: Section | "setup"): Catalogue {
  const [x, f] = frame(v, workspace, "synthetic_notes_catalogue"), p = obj(x.pages), keys = expected === "setup" ? ["notes", "sources", "parties", "policies", "requests"] : [expected];
  if (Object.keys(p).length !== keys.length || keys.some(key => !Object.hasOwn(p, key))) return fail();
  const pages: Pages = {};
  if (p.notes) pages.notes = page(p.notes, noteRow);
  if (p.sources) pages.sources = page(p.sources, choice);
  if (p.parties) pages.parties = page(p.parties, choice);
  if (p.policies) pages.policies = page(p.policies, policy);
  if (p.requests) pages.requests = { ...page(p.requests, parseRequest), pending_count: integer(obj(p.requests).pending_count, 0, Number.MAX_SAFE_INTEGER) };
  return { ...f, pages };
}
export type ReferencedNote = Pick<Inspection, "item" | "references">;
function referencedNote(v: unknown, workspace: string, record: string): ReferencedNote {
  const x = obj(v), n = obj(x.item), r = obj(x.references);
  if (id(n.id) !== record || id(n.workspace_id) !== workspace || !["draft", "confirmed"].includes(String(n.state)) || !["observation", "question", "decision", "action"].includes(String(n.kind)) || typeof n.marker !== "string" || !/^synthetic:[a-zA-Z0-9 _.-]+$/.test(n.marker) || n.marker.length > 256 || !Array.isArray(n.source_ids) || n.source_ids.length > 10) return fail();
  const sources = n.source_ids.map(id), selected = (Array.isArray(r.sources) ? r.sources : fail()).map(choice), ownerId = n.owner_id === null ? null : id(n.owner_id), p = policy(r.policy);
  if (new Set(sources).size !== sources.length || selected.length !== sources.length || new Set(selected.map(s => s.id)).size !== selected.length || selected.some(s => !sources.includes(s.id)) || p.id !== id(n.policy_id)) return fail();
  let owner: Inspection["references"]["owner"] = null;
  if (r.owner !== null) { const o = obj(r.owner); owner = { id: id(o.id), available: bool(o.available), label: o.label === null ? null : label(o.label) }; if (owner.available !== (owner.label !== null)) return fail(); }
  if ((owner?.id ?? null) !== ownerId) return fail();
  return { item: { id: record, workspace_id: workspace, policy_id: p.id, revision: integer(n.revision, 1, 100), state: n.state as Note["state"], kind: n.kind as Draft["kind"], marker: n.marker, source_ids: sources, owner_id: ownerId, due_at: n.due_at === null ? null : date(n.due_at), retain_until: date(n.retain_until), actor_id: id(n.actor_id), created_at: date(n.created_at), updated_at: date(n.updated_at) }, references: { sources: selected, owner, policy: p } };
}
export function parseInspection(v: unknown, workspace: string, record: string): Inspection {
  const [x, f] = frame(v, workspace, "synthetic_note_inspection");
  if (typeof x.payload_hash !== "string" || !/^[a-f0-9]{64}$/.test(x.payload_hash)) return fail();
  return { ...f, ...referencedNote(x, workspace, record), payload_hash: x.payload_hash };
}

export type ExportSelection = { id: string; expected_revision: number };
export type ExportRequest = { selections: ExportSelection[]; include_drafts: boolean; purpose: "preview" | "download"; acknowledge_copy_limits?: boolean; reviewed_hash?: string };
export type NotesArchive = { schema_version: 1; mode: "synthetic_work_notes_archive"; workspace_id: string; export_id: string; generated_at: string; retain_until: string; current_revisions_only: true; managed_copy: false; execution_allowed: false; raw_transcripts_included: false; drafts_permitted: boolean; items: ReferencedNote[] };
export type NotesExport = Frame & { bundle: NotesArchive; bundle_bytes: number; reviewed_hash: string; purpose: "preview" | "download"; request: ExportRequest };
export function parseExport(v: unknown, workspace: string, request: ExportRequest): NotesExport {
  const [x, f] = frame(v, workspace, "synthetic_notes_export"), b = obj(x.bundle);
  if (!f.features.export || x.purpose !== request.purpose || b.schema_version !== 1 || b.mode !== "synthetic_work_notes_archive" || id(b.workspace_id) !== workspace || b.current_revisions_only !== true || b.managed_copy !== false || b.execution_allowed !== false || b.raw_transcripts_included !== false || bool(b.drafts_permitted) !== request.include_drafts || typeof x.reviewed_hash !== "string" || !/^[a-f0-9]{64}$/.test(x.reviewed_hash)) return fail();
  if (request.purpose === "download" && (request.acknowledge_copy_limits !== true || x.reviewed_hash !== request.reviewed_hash)) return fail();
  if (!Array.isArray(b.items) || !b.items.length || b.items.length > 10 || b.items.length !== request.selections.length || new Set(request.selections.map(s => s.id)).size !== request.selections.length) return fail();
  const generated = date(b.generated_at), retention = date(b.retain_until);
  if (Date.parse(generated) > Date.parse(f.checked_at) || Date.parse(retention) <= Date.parse(f.checked_at) || Date.parse(f.valid_until) > Date.parse(retention)) return fail();
  const items = b.items.map((item, index) => {
    const selected = request.selections[index], value = referencedNote(item, workspace, selected.id), n = value.item;
    if (n.revision !== selected.expected_revision || !n.source_ids.length || (!request.include_drafts && n.state !== "confirmed") || Date.parse(n.retain_until) < Date.parse(retention) || Date.parse(n.created_at) > Date.parse(n.updated_at) || Date.parse(n.updated_at) > Date.parse(f.checked_at)) return fail();
    return value;
  });
  const bundle: NotesArchive = { schema_version: 1, mode: "synthetic_work_notes_archive", workspace_id: workspace, export_id: id(b.export_id), generated_at: generated, retain_until: retention, current_revisions_only: true, managed_copy: false, execution_allowed: false, raw_transcripts_included: false, drafts_permitted: request.include_drafts, items };
  const size = integer(x.bundle_bytes, 1, 32768);
  if (new TextEncoder().encode(JSON.stringify(bundle)).length !== size) return fail();
  return { ...f, bundle, bundle_bytes: size, reviewed_hash: x.reviewed_hash, purpose: request.purpose, request: { ...request, selections: request.selections.map(s => ({ ...s })) } };
}
export async function prepareExport(workspace: string, request: ExportRequest, session: Session, signal: AbortSignal): Promise<NotesExport> {
  return parseExport(await post(workspace, "/notes/export", request, session, signal), workspace, request);
}

async function post(workspace: string, path: string, body: object, session: Session, signal: AbortSignal): Promise<unknown> {
  id(workspace);
  const response = await fetch(`/api/v1/work/workspaces/${workspace}${path}`, { method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", signal, headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrfToken }, body: JSON.stringify(body) });
  if (!response.ok) throw new NotesError(response.status);
  return response.json();
}
export async function catalogue(workspace: string, session: Session, signal: AbortSignal, section: Section | "setup" = "setup", after: string | null = null, recover?: Pick<Action, "request_id" | "operation">): Promise<Catalogue> {
  return parseCatalogue(await post(workspace, "/notes/catalogue", { section, ...(after ? { after } : {}), ...(recover ? { request_id: recover.request_id, operation: recover.operation } : {}) }, session, signal), workspace, section);
}
export async function inspect(workspace: string, record: string, session: Session, signal: AbortSignal): Promise<Inspection> { id(record); return parseInspection(await post(workspace, `/notes/${record}/inspect`, {}, session, signal), workspace, record); }
function ack(v: unknown, action: Action): Ack {
  const x = obj(v), confirmation = action.operation === "confirm_note", capture = action.operation === "capture_draft";
  const mode = confirmation ? "synthetic_note_confirmation" : capture ? "synthetic_draft_capture" : "synthetic_note_change";
  if (x.schema_version !== 1 || x.mode !== mode || !["pending", "applied", "denied"].includes(String(x.state)) || x.execution_allowed !== false || x.model_invoked !== false || (!confirmation && x.real_ingestion_allowed !== false) || (!capture && !confirmation && x.operation !== action.operation)) return fail();
  const requestId = id(confirmation ? x.confirmation_request_id : capture ? x.capture_preparation_id : x.change_request_id);
  const applied = bool(confirmation ? x.confirmation_applied : capture ? x.capture_applied : x.change_applied);
  if (applied !== (x.state === "applied")) return fail();
  const revision = confirmation ? x.applied_revision : x.revision, record = confirmation ? (applied ? action.target_record_id : null) : x.record_id;
  if (applied ? integer(revision, 1, 101) !== (capture ? 1 : action.expected_revision! + 1) || !record || (!capture && record !== action.target_record_id) : revision !== null || record !== null) return fail();
  return { id: requestId, state: x.state as Ack["state"], record_id: record === null ? null : id(record), revision: revision as number | null, expires_at: date(x.expires_at) };
}
export async function submit(workspace: string, action: Action, session: Session, signal: AbortSignal): Promise<Ack> {
  if (action.review && !action.review.receipt) {
    const r = obj(await post(workspace, `/drafts/${id(action.target_record_id)}/review`, action.review.body, session, signal));
    if (r.mode !== "synthetic_review_preparation" || r.schema_version !== 1 || r.workspace_id !== workspace || r.record_id !== action.target_record_id || r.revision !== action.expected_revision || r.confirmation_applied !== false || r.execution_allowed !== false || r.model_invoked !== false) return fail();
    const receipt = id(r.review_preparation_id); date(r.expires_at);
    action.review.receipt = receipt;
    action.body = { ...action.body, review_preparation_id: receipt };
  }
  const path = action.operation === "capture_draft" ? "/captures" : `/drafts/${id(action.target_record_id)}/${action.operation === "correct_note" ? "correct" : action.operation === "forget_note" ? "forget" : "confirm"}`;
  return ack(await post(workspace, path, action.body, session, signal), action);
}
export function recovered(page: Page<RequestRow>, action: Pick<Action, "operation" | "request_id" | "target_record_id" | "expected_revision">): RequestRow | null {
  if (!page.items.length) return null;
  if (page.items.length !== 1) return fail();
  const row = page.items[0];
  if (row.operation !== action.operation || row.request_id !== action.request_id || row.target_record_id !== action.target_record_id || row.expected_revision !== action.expected_revision) return fail();
  return row;
}
