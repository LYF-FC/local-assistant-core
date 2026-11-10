import type { Session } from "./api";
import * as tasks from "./tasks-api";
import * as documents from "./documents-api";

export type SearchKind = "task" | "document";
export type SearchSelection = { scope: tasks.TaskScope; query: string };
export type SourceTarget = { kind: SearchKind; id: string; owner_id: string; scope: tasks.TaskScope; revision: number; created_at: string };
export type SearchHit = { target: SourceTarget; title: string; source: string; status: string };
export type SearchPage = { checkedAt: string; items: SearchHit[]; nextCursor: string | null };
export type SearchSection = { state: "available"; page: SearchPage } | { state: "unavailable" };
export type SearchResult = { selection: SearchSelection; startedAt: number; tasks: SearchSection; documents: SearchSection };
export type CurrentSource = { kind: "task"; record: tasks.ActiveTask } | { kind: "document"; record: documents.Document };
export class SearchDenied extends Error { constructor(public status: number) { super("Search access is no longer available. Reload your session before searching again."); } }
function invalid(): never { throw new Error("Invalid search source or receipt"); }
const uuid = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const date = (v: unknown): v is string => typeof v === "string" && v.length <= 40 && Number.isFinite(Date.parse(v));
export function validQuery(value: string): boolean { return value.trim().length > 0 && Array.from(value).length <= 160 && !/[\u0000-\u001f\u007f\ud800-\udfff]/u.test(value); }
function allowed(session: Session, scope: tasks.TaskScope) { if (!Object.hasOwn(tasks.taskScopes, scope) || !session.user.scopes.includes(scope)) throw new SearchDenied(403); }
function checked(value: string) { if (!date(value) || Date.parse(value) < Date.now() - 60000 || Date.parse(value) > Date.now() + 5000) invalid(); }
function owner(session: Session, row: { owner_id: string; scope: tasks.TaskScope; can_edit: boolean }, scope: tasks.TaskScope) {
  if (row.scope !== scope || (scope !== "household_shared" && row.owner_id !== session.user.id) || row.can_edit !== (row.owner_id === session.user.id)) invalid();
}
export function targetOf(source: CurrentSource): SourceTarget { const row = source.record; return { kind: source.kind, id: row.id, owner_id: row.owner_id, scope: row.scope, revision: row.revision, created_at: row.created_at }; }
function code(error: unknown): number | null { return error instanceof tasks.TaskError || error instanceof documents.DocumentError || error instanceof SearchDenied ? error.status : null; }
function rejectDenial(error: unknown) { const status = code(error); if (status !== null && [401,403,404,410].includes(status)) throw new SearchDenied(status); }
export async function searchPage(session: Session, selection: SearchSelection, kind: SearchKind, after: string | null, signal: AbortSignal): Promise<SearchPage> {
  allowed(session, selection.scope);
  if (!validQuery(selection.query) || (after !== null && !uuid(after))) invalid();
  try {
    if (kind === "task") {
      const page = await tasks.listTasks({ scope: selection.scope, search: selection.query, status: "all", due: "all", after }, session.csrfToken, signal);
      checked(page.checked_at);
      page.items.forEach(row => owner(session, row, selection.scope));
      return { checkedAt: page.checked_at, nextCursor: page.next_cursor, items: page.items.map(row => ({ target: targetOf({ kind, record: row }), title: row.title, source: row.source_reference, status: `Task · ${row.status}` })) };
    }
    if (kind !== "document") invalid();
    const page = await documents.list({ scope: selection.scope, search: selection.query, reviewed_only: false, after }, session.csrfToken, signal);
    checked(page.checked_at);
    if (page.actor_id !== session.user.id) invalid();
    page.items.forEach(row => { owner(session, row, selection.scope); if (row.state !== "active") invalid(); });
    return { checkedAt: page.checked_at, nextCursor: page.next_cursor, items: page.items.map(row => ({ target: targetOf({ kind, record: row }), title: row.title!, source: row.source_reference!, status: `Document · ${row.reviewed ? "reviewed text" : "text review needed"}${row.extraction && row.extraction.status !== "ready" ? ` · extraction ${row.extraction.status}` : ""}` })) };
  } catch (error) { rejectDenial(error); throw error; }
}
export async function searchRecords(session: Session, selection: SearchSelection, signal: AbortSignal): Promise<SearchResult> {
  allowed(session, selection.scope);
  if (!validQuery(selection.query)) invalid();
  const startedAt = Date.now();
  const [taskResult, documentResult] = await Promise.allSettled([searchPage(session, selection, "task", null, signal), searchPage(session, selection, "document", null, signal)]);
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  for (const result of [taskResult, documentResult]) if (result.status === "rejected") rejectDenial(result.reason);
  const section = (result: PromiseSettledResult<SearchPage>): SearchSection => result.status === "fulfilled" ? { state: "available", page: result.value } : { state: "unavailable" };
  return { selection: { ...selection }, startedAt, tasks: section(taskResult), documents: section(documentResult) };
}
export async function readSearchSource(session: Session, target: SourceTarget, signal: AbortSignal, includeDocumentBody = false): Promise<CurrentSource> {
  allowed(session, target.scope);
  if (!["task", "document"].includes(target.kind) || !uuid(target.id) || !uuid(target.owner_id) || !Number.isSafeInteger(target.revision) || target.revision < 1 || !date(target.created_at) || (target.scope !== "household_shared" && target.owner_id !== session.user.id)) invalid();
  const response = await fetch(`/api/v1/${target.kind === "task" ? "tasks" : "documents"}/${target.id}/read`, { method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", signal, headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrfToken }, body: JSON.stringify({ scope: target.scope }) });
  if (!response.ok) { if ([401,403,404,410].includes(response.status)) throw new SearchDenied(response.status); throw new Error("Current source unavailable"); }
  const value: unknown = await response.json();
  const row = target.kind === "task" ? tasks.parseTask(value) : documents.parseDocument(value, true);
  if (row.state === "forgotten") throw new SearchDenied(410);
  owner(session, row, target.scope);
  if (row.id !== target.id || row.owner_id !== target.owner_id || row.created_at !== target.created_at || row.revision < target.revision) invalid();
  if (target.kind === "task") return { kind: "task", record: row as tasks.ActiveTask };
  if (includeDocumentBody) return { kind: "document", record: row as documents.Document };
  // Existing read receipt includes the body; neither search state nor navigation retains it.
  const { content_text: _body, ...metadata } = row as documents.Document;
  return { kind: "document", record: metadata };
}
