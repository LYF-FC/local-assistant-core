// Unified attention inbox (spec 071): a read-and-link composition of existing protected reads for
// one granted scope. It issues only read queries, holds only minimal card fields in memory, and can
// never decide, cancel, consume, retry, acknowledge, file, send or complete anything.
import type { Session } from "./api";
import { AttentionError, listApprovals, type ApprovalPage, listFiling, listNotifications, type FailureState } from "./attention-api";
import type { Destination } from "./daily-overview";
import { DocumentError, list as listDocuments, type Document, type DocumentIdentity } from "./documents-api";
import type { SourceTarget } from "./record-search";
import { listReminders, ReminderError } from "./reminders-api";
import { listTasks, TaskError, taskScopes, type TaskScope } from "./tasks-api";

export const SOURCES = ["approvals", "filing_failed", "filing_unknown", "notifications_failed", "notifications_unknown", "documents", "reminders", "tasks"] as const;
export type SourceKey = (typeof SOURCES)[number];
export type Kind = "approval" | "filing" | "notification" | "document" | "reminder" | "task";
export type Open = { type: "source"; target: SourceTarget } | { type: "destination"; destination: Destination } | { type: "document"; target: DocumentIdentity } | { type: "reminder"; scope: TaskScope; task_id: string };
export type Card = {
  key: string; kind: Kind; id: string; scope: TaskScope; revision: number;
  title: string; status: string; labels: string[]; evidence: string[]; uncertainty: string[];
  readAt: string; open: Open | null; openNote: string | null; expiresAt: string | null; changedDuringRefresh: boolean;
};
export type Source = { state: "available"; readAt: string; cards: Card[]; more: boolean; notice: string | null; cursor?: string | null } | { state: "unavailable" };
export type Inbox = { scope: TaskScope; startedAt: number; expiresAt: number; sources: Record<SourceKey, Source> };
export class InboxDenied extends Error {
  constructor(public status: number) { super("Inbox access is no longer available. Refresh your session before retrying."); }
}
export const VIEW_LIFETIME_MS = 60_000;
const NO_APPROVAL_SCREEN = "No approvals screen is available in this release; this card cannot be opened or acted on here.";

function statusOf(error: unknown): number | null {
  return error instanceof AttentionError || error instanceof TaskError || error instanceof DocumentError || error instanceof ReminderError ? error.status : null;
}
export function isDenial(status: number | null): boolean { return status !== null && [401, 403, 404, 410].includes(status); }
const words = (value: string) => value.replace(/_/g, " ");
const card = (partial: Pick<Card, "kind" | "id" | "scope" | "revision" | "title" | "status" | "readAt"> & Partial<Card>): Card => ({
  labels: [], evidence: [], uncertainty: [], open: null, openNote: null, expiresAt: null, changedDuringRefresh: false, key: `${partial.kind}:${partial.id}`, ...partial,
});

function approvalCards(page: ApprovalPage, scope: TaskScope): Card[] {
  return page.items.map(row => card({
    kind: "approval", id: row.id, scope, revision: 0, title: `Approval request (${row.action_type})`, status: "Awaiting a decision", readAt: page.checked_at,
    labels: [row.requested_by_you ? "Requested by you" : "Requested by another member of this scope"],
    evidence: [`Requested ${row.requested_at}`, `Expires ${row.expires_at}`],
    uncertainty: ["The stored status is read-only here and may change before it is opened elsewhere."],
    openNote: NO_APPROVAL_SCREEN, expiresAt: row.expires_at,
  }));
}

async function read(key: SourceKey, session: Session, scope: TaskScope, signal: AbortSignal): Promise<Source> {
  const csrf = session.csrfToken;
  switch (key) {
    case "approvals": {
      const page = await listApprovals(scope, session, signal);
      return { state: "available", readAt: page.checked_at, more: page.next_cursor !== null, cursor: page.next_cursor, notice: null, cards: approvalCards(page, scope) };
    }
    case "filing_failed": case "filing_unknown": {
      const state: FailureState = key === "filing_failed" ? "failed" : "unknown";
      const page = await listFiling(scope, state, session, signal);
      return { state: "available", readAt: page.checked_at, more: page.next_cursor !== null, notice: page.notice, cards: page.items.map(row => card({
        kind: "filing", id: row.id, scope, revision: row.revision, title: "Filing request", status: state === "failed" ? "Filing failed" : "Outcome not confirmed", readAt: page.checked_at,
        evidence: [`${row.attempts} attempt${row.attempts === 1 ? "" : "s"}`, `Updated ${row.updated_at}`, ...(row.reason ? [`Reason: ${words(row.reason)}`] : [])],
        uncertainty: state === "unknown" ? ["The filing outcome was not confirmed. Check the document before repeating anything."] : [],
        open: row.document_id && row.owner_id ? { type: "document", target: { id: row.document_id, owner_id: row.owner_id, scope, min_revision: row.source_revision! } } : null,
        openNote: row.document_id ? null : "The related document is no longer linked.",
      })) };
    }
    case "notifications_failed": case "notifications_unknown": {
      const state: FailureState = key === "notifications_failed" ? "failed" : "unknown";
      const page = await listNotifications(scope, state, session, signal);
      return { state: "available", readAt: page.checked_at, more: page.next_cursor !== null, notice: null, cards: page.items.map(row => card({
        kind: "notification", id: row.id, scope, revision: row.revision, title: `Reminder notification (${row.channel})`, status: state === "failed" ? "Delivery failed" : "Delivery not confirmed", readAt: page.checked_at,
        evidence: [`${row.attempts} attempt${row.attempts === 1 ? "" : "s"}`, `Updated ${row.updated_at}`, ...(row.reason ? [`Reason: ${words(row.reason)}`] : [])],
        uncertainty: state === "unknown" ? ["Delivery was not confirmed; the reminder may or may not have been shown."] : [],
        open: row.task_id ? { type: "reminder", scope, task_id: row.task_id } : null,
        openNote: row.task_id ? null : "The related reminder is not available to open.",
      })) };
    }
    case "documents": {
      const page = await listDocuments({ scope, reviewed_only: false, search: "", after: null }, csrf, signal);
      if (page.actor_id !== session.user.id || (scope !== "household_shared" && page.items.some(row => row.owner_id !== session.user.id))) throw new Error("Invalid document projection");
      return { state: "available", readAt: page.checked_at, more: page.next_cursor !== null, notice: null, cards: page.items.flatMap(row => {
        const labels = documentLabels(row);
        if (!labels.length) return [];
        const target: SourceTarget = { kind: "document", id: row.id, owner_id: row.owner_id, scope, revision: row.revision, created_at: row.created_at };
        return [card({
          kind: "document", id: row.id, scope, revision: row.revision, title: row.title ?? "Document", status: "Needs review", labels, readAt: page.checked_at,
          evidence: [`Revision ${row.revision}`, row.can_edit ? "You can review this document in Documents" : "Read-only for you; the creator reviews it"],
          uncertainty: ["Text and extraction review only; this is not invoice-field or filing approval."], open: { type: "source", target },
        })];
      }) };
    }
    case "reminders": {
      const page = await listReminders({ scope, state: "delivered", after: null }, session, signal);
      return { state: "available", readAt: page.checked_at, more: page.next_cursor !== null, notice: null, cards: page.items.map(({ reminder, task }) => card({
        kind: "reminder", id: reminder.id, scope, revision: reminder.revision, title: task.state === "active" ? task.title : "Task no longer available", status: "Delivered, not acknowledged", readAt: page.checked_at,
        evidence: [`Scheduled ${reminder.scheduled_at}`, ...(reminder.delivered_at ? [`Delivered ${reminder.delivered_at}`] : [])],
        uncertainty: ["Delivered in-app does not mean it was seen. Acknowledge it in My reminders."],
        open: { type: "destination", destination: { view: "reminders", scope } },
      })) };
    }
    case "tasks": {
      const page = await listTasks({ scope, status: "open", due: "overdue", search: "", after: null }, csrf, signal);
      if (scope !== "household_shared" && page.items.some(row => row.owner_id !== session.user.id)) throw new Error("Invalid task projection");
      return { state: "available", readAt: page.checked_at, more: page.next_cursor !== null, notice: null, cards: page.items.map(row => card({
        kind: "task", id: row.id, scope, revision: row.revision, title: row.title, status: "Open, overdue", readAt: page.checked_at,
        evidence: [`Due ${row.due_at}`, row.can_edit ? "You can update this task in Tasks" : "Shared task; read-only for you"],
        open: { type: "source", target: { kind: "task", id: row.id, owner_id: row.owner_id, scope, revision: row.revision, created_at: row.created_at } },
      })) };
    }
  }
}
export function documentLabels(row: Document): string[] {
  if (row.state !== "active") return [];
  const labels: string[] = [];
  if (row.extraction && row.extraction.status !== "ready") {
    labels.push(({ no_text: "No text extracted", encrypted: "Encrypted original", invalid: "Invalid PDF", resource_limit: "Parser limit reached", unavailable: "Parser unavailable" } as const)[row.extraction.status]);
  }
  if (!row.reviewed) labels.push("Text review needed");
  return labels;
}
async function settle(key: SourceKey, session: Session, scope: TaskScope, signal: AbortSignal): Promise<Source> {
  try { return await read(key, session, scope, signal); } catch (error) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    if (isDenial(statusOf(error))) throw new InboxDenied(statusOf(error)!);
    return { state: "unavailable" };
  }
}
export function deadline(startedAt: number, sources: Record<SourceKey, Source>): number {
  let end = startedAt + VIEW_LIFETIME_MS;
  const approvals = sources.approvals;
  if (approvals.state === "available") for (const row of approvals.cards) if (row.expiresAt) end = Math.min(end, Date.parse(row.expiresAt));
  return end;
}
export async function loadInbox(session: Session, scope: TaskScope, signal: AbortSignal, now = () => Date.now()): Promise<Inbox> {
  if (!Object.hasOwn(taskScopes, scope) || !session.user.scopes.includes(scope)) throw new InboxDenied(403);
  const startedAt = now();
  const results = await Promise.all(SOURCES.map(key => settle(key, session, scope, signal)));
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  const sources = Object.fromEntries(SOURCES.map((key, i) => [key, results[i]])) as Record<SourceKey, Source>;
  return { scope, startedAt, expiresAt: deadline(startedAt, sources), sources };
}
// Retry re-reads exactly one source. It can shorten the view's deadline but never extend it.
export async function retrySource(inbox: Inbox, key: SourceKey, session: Session, signal: AbortSignal): Promise<Inbox> {
  if (!session.user.scopes.includes(inbox.scope)) throw new InboxDenied(403);
  const next = await settle(key, session, inbox.scope, signal);
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  const sources = { ...inbox.sources, [key]: next };
  return { ...inbox, sources, expiresAt: Math.min(inbox.expiresAt, deadline(inbox.startedAt, sources)) };
}

// A record that changed state between the failed and unknown reads appears once; the higher
// revision wins, on a tie the later read wins, and the card is flagged. Different record kinds are never merged.
export type Group = { id: "approvals" | "filing" | "notifications" | "documents" | "reminders" | "tasks"; title: string; unavailable: SourceKey[]; cards: Card[]; more: boolean; pageable: boolean; notices: string[] };
export function merge(...lists: Card[][]): Card[] {
  const byKey = new Map<string, Card>();
  for (const row of lists.flat()) {
    const held = byKey.get(row.key);
    if (!held) { byKey.set(row.key, row); continue; }
    const winner = row.revision >= held.revision ? row : held;
    byKey.set(row.key, { ...winner, changedDuringRefresh: true });
  }
  return [...byKey.values()];
}
export function groups(inbox: Inbox): Group[] {
  const pick = (...keys: SourceKey[]) => {
    const parts = keys.map(key => ({ key, source: inbox.sources[key] }));
    const available = parts.flatMap(part => part.source.state === "available" ? [part.source] : []);
    return {
      unavailable: parts.filter(part => part.source.state === "unavailable").map(part => part.key),
      cards: merge(...available.map(source => source.cards)),
      more: available.some(source => source.more),
      pageable: available.some(source => source.more && !!source.cursor),
      notices: [...new Set(available.flatMap(source => source.notice ? [source.notice] : []))],
    };
  };
  return [
    { id: "approvals", title: "Pending approvals", ...pick("approvals") },
    { id: "filing", title: "Failures: filing", ...pick("filing_failed", "filing_unknown") },
    { id: "notifications", title: "Failures: notifications", ...pick("notifications_failed", "notifications_unknown") },
    { id: "documents", title: "Documents needing review", ...pick("documents") },
    { id: "reminders", title: "Delivered reminders", ...pick("reminders") },
    { id: "tasks", title: "Overdue open tasks", ...pick("tasks") },
  ];
}
// Explicit, user-requested next approvals page using the existing cursor. It appends to the held
// section, never extends the view deadline, and any failure leaves the held cards untouched.
export async function moreApprovals(inbox: Inbox, session: Session, signal: AbortSignal): Promise<Inbox> {
  if (!session.user.scopes.includes(inbox.scope)) throw new InboxDenied(403);
  const held = inbox.sources.approvals;
  if (held.state !== "available" || !held.cursor) return inbox;
  let page;
  try { page = await listApprovals(inbox.scope, session, signal, held.cursor); } catch (error) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    if (isDenial(statusOf(error))) throw new InboxDenied(statusOf(error)!);
    throw error;
  }
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  const next = approvalCards(page, inbox.scope);
  const sources = { ...inbox.sources, approvals: { ...held, readAt: page.checked_at, more: page.next_cursor !== null, cursor: page.next_cursor, cards: merge(held.cards, next) } };
  return { ...inbox, sources, expiresAt: Math.min(inbox.expiresAt, deadline(inbox.startedAt, sources)) };
}

// Honest per-section wording for "more records exist". Existing is not the same as reachable:
// only approvals can be paged inside the inbox; the other sections say where, if anywhere, the
// rest can be seen. No destination is promised that cannot show the records.
export const MORE_TEXT: Record<Group["id"], string> = {
  approvals: "More pending approvals exist than are shown. Use Load more approvals to read the next page; this is not a complete count.",
  filing: "More failed or unconfirmed filing requests exist than this first page shows. No screen in this release lists filing requests, so the rest cannot be viewed from here.",
  notifications: "More failed or unconfirmed reminder notifications exist than this first page shows. No screen in this release lists notification deliveries, so the rest cannot be viewed from here.",
  documents: "More documents exist than this first page shows. The Documents view lists documents for this scope.",
  reminders: "More delivered reminders exist than this first page shows. The Reminders view lists reminders for this scope.",
  tasks: "More overdue tasks may exist than this first page shows. The Tasks view lists tasks for this scope.",
};
export function emptyState(inbox: Inbox): "none" | "unavailable" | null {
  const all = SOURCES.map(key => inbox.sources[key]);
  const unavailable = all.some(source => source.state === "unavailable");
  const empty = groups(inbox).every(group => !group.cards.length);
  if (unavailable) return empty ? "unavailable" : null;
  return empty ? "none" : null;
}
export const EMPTY_TEXT = { none: "Nothing needs attention in the sources that loaded.", unavailable: "Some sources are unavailable. Nothing is shown for them, which does not mean nothing needs attention." } as const;
export function expired(inbox: Inbox, now = Date.now()): boolean { return now >= inbox.expiresAt; }
export function earliestApprovalExpiry(inbox: Inbox): number | null {
  const approvals = inbox.sources.approvals;
  const times = approvals.state === "available" ? approvals.cards.flatMap(row => row.expiresAt ? [Date.parse(row.expiresAt)] : []) : [];
  return times.length ? Math.min(...times) : null;
}
