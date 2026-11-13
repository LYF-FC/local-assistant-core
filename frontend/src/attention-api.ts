// Read-only clients for the three sources the attention inbox adds (spec 071). Every parser is a
// strict allow-list: an unexpected key, scope, owner, state or order makes the whole source
// unavailable, so a payload, hash or another person's identifier can never enter inbox state.
import type { Session } from "./api";
import { taskScopes, type TaskScope } from "./tasks-api";

export class AttentionError extends Error {
  constructor(public status: number) { super([401, 403, 404, 410].includes(status) ? "Inbox access is no longer available. Reload your session before refreshing." : "A source is unavailable."); }
}
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const uuid = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const date = (v: unknown): v is string => typeof v === "string" && v.length <= 40 && Number.isFinite(Date.parse(v));
const nullableDate = (v: unknown) => v === null || date(v);
const count = (v: unknown, min = 0): v is number => Number.isSafeInteger(v) && (v as number) >= min;
const word = (v: unknown, max = 128): v is string => typeof v === "string" && v.length > 0 && v.length <= max;
function invalid(): never { throw new Error("Invalid inbox source response"); }
function exactKeys(v: Record<string, unknown>, keys: string[]) {
  if (Object.keys(v).length !== keys.length || keys.some(key => !Object.hasOwn(v, key))) invalid();
}
function ordered(ids: string[], after: string | null, next: unknown) {
  if (new Set(ids).size !== ids.length || ids.some((id, i) => (i > 0 && id <= ids[i - 1]) || (after !== null && id <= after))) invalid();
  if (!(next === null || uuid(next)) || (next !== null && (ids.length !== 25 || ids[24] !== next))) invalid();
}
async function post(path: string, body: object, session: Session, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", signal, headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrfToken }, body: JSON.stringify(body) });
  if (!response.ok) throw new AttentionError(response.status);
  return response.json();
}
function envelope(v: unknown, scope: TaskScope, keys: string[]): Record<string, unknown> {
  if (!object(v) || !Object.hasOwn(taskScopes, scope)) invalid();
  exactKeys(v, keys);
  if (v.schema_version !== 1 || !date(v.checked_at) || !Array.isArray(v.items) || v.items.length > 25) invalid();
  return v;
}

export type ApprovalItem = { id: string; scope: TaskScope; action_type: string; status: "pending"; requested_at: string; expires_at: string; requested_by_you: boolean };
export type ApprovalPage = { checked_at: string; items: ApprovalItem[]; next_cursor: string | null };
const APPROVAL_KEYS = ["id", "scope", "action_type", "status", "requested_at", "expires_at", "requested_by_you"];
export function parseApprovalPage(v: unknown, scope: TaskScope): ApprovalPage {
  const page = envelope(v, scope, ["schema_version", "mode", "checked_at", "page_limit", "items", "next_cursor"]);
  if (page.mode !== "approval_page" || page.page_limit !== 25) invalid();
  const items = (page.items as unknown[]).map((row): ApprovalItem => {
    if (!object(row)) invalid();
    exactKeys(row, APPROVAL_KEYS);
    if (!uuid(row.id) || row.scope !== scope || !word(row.action_type) || row.status !== "pending" || !date(row.requested_at) || !date(row.expires_at) || typeof row.requested_by_you !== "boolean") invalid();
    return { id: row.id, scope, action_type: row.action_type, status: "pending", requested_at: row.requested_at, expires_at: row.expires_at, requested_by_you: row.requested_by_you };
  });
  ordered(items.map(row => row.id), null, page.next_cursor);
  return { checked_at: page.checked_at as string, items, next_cursor: page.next_cursor as string | null };
}
export async function listApprovals(scope: TaskScope, session: Session, signal: AbortSignal): Promise<ApprovalPage> {
  return parseApprovalPage(await post("/api/v1/approvals/query", { scope }, session, signal), scope);
}

export type FailureState = "failed" | "unknown";
export type FilingItem = { id: string; document_id: string | null; state: FailureState; revision: number; attempts: number; reason: string | null; updated_at: string; scrubbed: boolean };
export type FilingPage = { checked_at: string; state: FailureState; items: FilingItem[]; next_cursor: string | null; notice: string };
const FILING_KEYS = ["id", "document_id", "owner_id", "scope", "destination", "state", "revision", "plan_revision", "source_revision", "attempts", "next_attempt_at", "resolved_at", "reason", "created_at", "updated_at", "scrubbed"];
export function parseFilingPage(v: unknown, scope: TaskScope, state: FailureState, session: Session): FilingPage {
  const page = envelope(v, scope, ["schema_version", "checked_at", "owner_id", "scope", "state", "items", "next_cursor", "notice"]);
  if (page.owner_id !== session.user.id || page.scope !== scope || page.state !== state || !word(page.notice, 200)) invalid();
  const items = (page.items as unknown[]).map((row): FilingItem => {
    if (!object(row)) invalid();
    exactKeys(row, FILING_KEYS);
    if (!uuid(row.id) || row.owner_id !== session.user.id || row.scope !== scope || row.state !== state || !count(row.revision, 1) || !count(row.attempts) || !nullableDate(row.next_attempt_at) || !nullableDate(row.resolved_at) || !(row.reason === null || word(row.reason, 256)) || !date(row.created_at) || !date(row.updated_at) || typeof row.scrubbed !== "boolean" || !(row.document_id === null ? row.scrubbed : uuid(row.document_id) && !row.scrubbed)) invalid();
    return { id: row.id, document_id: row.document_id as string | null, state, revision: row.revision, attempts: row.attempts, reason: row.reason as string | null, updated_at: row.updated_at, scrubbed: row.scrubbed };
  });
  ordered(items.map(row => row.id), null, page.next_cursor);
  return { checked_at: page.checked_at as string, state, items, next_cursor: page.next_cursor as string | null, notice: page.notice as string };
}
export async function listFiling(scope: TaskScope, state: FailureState, session: Session, signal: AbortSignal): Promise<FilingPage> {
  return parseFilingPage(await post("/api/v1/filing/query", { scope, state, document_id: null, after: null }, session, signal), scope, state, session);
}

export type NotificationItem = { id: string; reminder_id: string; channel: string; state: FailureState; revision: number; attempts: number; reason: string | null; updated_at: string };
export type NotificationPage = { checked_at: string; state: FailureState; items: NotificationItem[]; next_cursor: string | null };
const NOTIFICATION_KEYS = ["id", "reminder_id", "owner_id", "scope", "channel", "state", "revision", "cycle", "attempts", "next_attempt_at", "resolved_at", "reason", "created_at", "updated_at"];
export function parseNotificationPage(v: unknown, scope: TaskScope, state: FailureState, session: Session): NotificationPage {
  const page = envelope(v, scope, ["schema_version", "checked_at", "owner_id", "scope", "state", "items", "next_cursor"]);
  if (page.owner_id !== session.user.id || page.scope !== scope || page.state !== state) invalid();
  const items = (page.items as unknown[]).map((row): NotificationItem => {
    if (!object(row)) invalid();
    exactKeys(row, NOTIFICATION_KEYS);
    if (!uuid(row.id) || !uuid(row.reminder_id) || row.owner_id !== session.user.id || row.scope !== scope || !word(row.channel, 64) || row.state !== state || !count(row.revision, 1) || !count(row.cycle, 1) || !count(row.attempts) || !nullableDate(row.next_attempt_at) || !nullableDate(row.resolved_at) || !(row.reason === null || word(row.reason, 256)) || !date(row.created_at) || !date(row.updated_at)) invalid();
    return { id: row.id, reminder_id: row.reminder_id, channel: row.channel, state, revision: row.revision, attempts: row.attempts, reason: row.reason as string | null, updated_at: row.updated_at };
  });
  ordered(items.map(row => row.id), null, page.next_cursor);
  return { checked_at: page.checked_at as string, state, items, next_cursor: page.next_cursor as string | null };
}
export async function listNotifications(scope: TaskScope, state: FailureState, session: Session, signal: AbortSignal): Promise<NotificationPage> {
  return parseNotificationPage(await post("/api/v1/notifications/query", { scope, state, after: null }, session, signal), scope, state, session);
}
