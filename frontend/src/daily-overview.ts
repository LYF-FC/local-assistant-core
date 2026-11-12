import type { Session } from "./api";
import { CalendarError, getBriefing, type AgendaCalendar, type AgendaEvent, type Briefing } from "./calendars-api";
import { DocumentError, list, type Document, type Page } from "./documents-api";
import { listReminders, ReminderError, type ReminderPage } from "./reminders-api";
import { taskScopes, type TaskScope } from "./tasks-api";

export type Selection = { scope: TaskScope; day: string; timezone: string };
export type Section<T> = { state: "available"; data: T } | { state: "unavailable" };
export type Overview = {
  selection: Selection;
  startedAt: string;
  expiresAt: string;
  briefing: Section<Briefing>;
  reminders: Section<ReminderPage>;
  documents: Section<Page>;
};
export type Destination =
  | { view: "calendar"; selection: Selection }
  | { view: "tasks" | "reminders"; scope: TaskScope }
  | { view: "documents"; scope: TaskScope; document?: Document };
export class OverviewDenied extends Error {
  constructor(public status: number) { super("Overview access is no longer available. Refresh your session before retrying."); }
}
export function localDay(now = new Date()): string {
  return `${now.getFullYear().toString().padStart(4, "0")}-${(now.getMonth() + 1).toString().padStart(2, "0")}-${now.getDate().toString().padStart(2, "0")}`;
}
export function displayTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}
export function validSelection(value: Selection): boolean {
  if (!Object.hasOwn(taskScopes, value.scope) || !/^\d{4}-\d{2}-\d{2}$/.test(value.day) || Number(value.day.slice(0, 4)) < 1 || !/^[A-Za-z0-9_+./-]{1,64}$/.test(value.timezone)) return false;
  const date = new Date(`${value.day}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value.day) return false;
  try { new Intl.DateTimeFormat("en", { timeZone: value.timezone }).format(date); return true; } catch { return false; }
}
function status(error: unknown): number | null {
  return error instanceof CalendarError || error instanceof DocumentError || error instanceof ReminderError ? error.status : null;
}
function section<T>(result: PromiseSettledResult<T>): Section<T> {
  return result.status === "fulfilled" ? { state: "available", data: result.value } : { state: "unavailable" };
}
export async function loadOverview(session: Session, selection: Selection, signal: AbortSignal): Promise<Overview> {
  if (!session.user.scopes.includes(selection.scope)) throw new OverviewDenied(403);
  if (!validSelection(selection)) throw new Error("Choose a valid day and IANA timezone.");
  const started = Date.now();
  const [briefing, reminders, documents] = await Promise.allSettled([
    getBriefing(selection.scope, selection.day, selection.timezone, session.csrfToken, signal, 1).then(value => {
      if (selection.scope !== "household_shared" && (value.calendars.some(row => row.owner_id !== session.user.id) || value.tasks.some(row => row.owner_id !== session.user.id))) throw new Error("Invalid private briefing");
      return value;
    }),
    listReminders({ scope: selection.scope, state: "all", after: null }, session, signal),
    list({ scope: selection.scope, reviewed_only: false, search: "", after: null }, session.csrfToken, signal).then(value => {
      if (value.actor_id !== session.user.id || (selection.scope !== "household_shared" && value.items.some(row => row.owner_id !== session.user.id))) throw new Error("Invalid document projection");
      // No original/excerpt body is retained in the overview or navigation target.
      return { ...value, items: value.items.map(({ content_text: _content, ...row }) => row) };
    }),
  ]);
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  for (const result of [briefing, reminders, documents]) {
    if (result.status === "rejected") {
      const code = status(result.reason);
      if (code !== null && [401, 403, 404, 410].includes(code)) throw new OverviewDenied(code);
    }
  }
  const expires = Math.min(started + 60_000, briefing.status === "fulfilled" ? Date.parse(briefing.value.valid_until) : Infinity);
  return { selection: { ...selection }, startedAt: new Date(started).toISOString(), expiresAt: new Date(expires).toISOString(), briefing: section(briefing), reminders: section(reminders), documents: section(documents) };
}
export function documentAttention(row: Document): string | null {
  if (row.state !== "active") return null;
  if (row.extraction && row.extraction.status !== "ready") {
    return ({ no_text: "No text extracted", encrypted: "Encrypted original", invalid: "Invalid PDF", resource_limit: "Parser limit reached", unavailable: "Parser unavailable" } as const)[row.extraction.status];
  }
  return row.reviewed ? null : "Text review needed";
}

// Honest wording per source state. A source that is not "available" never supports a free-day claim.
export function sourceNote(row: AgendaCalendar): string {
  const read = row.unreadable ? ` ${row.unreadable} stored item${row.unreadable === 1 ? "" : "s"} could not be read and ${row.unreadable === 1 ? "is" : "are"} not shown.` : "";
  const reason = row.blocked_reason ? ` (${row.blocked_reason})` : "";
  const when = row.as_of ? ` as of ${row.as_of}` : "";
  switch (row.source_state) {
    case undefined: return `${row.status}; ${row.covers_day ? "covers selected day" : "selected day not covered"}${row.stale ? "; stale last-known snapshot" : ""}.`;
    case "available": return `available${when}; ${row.mode === "provider" ? "synchronized copy, not a live provider check" : "imported snapshot, not a live provider check"}.${read}`;
    case "stale": return `stale${when}; events shown are last-known and may have changed.${read}`;
    case "unavailable": return `unavailable${when}; last-known events are shown and may be out of date.${read}`;
    case "blocked": return `sync blocked${reason}; the last stored data is shown and may be incomplete until the owner resolves it.${read}`;
    case "limit_reached": return `limit reached${reason}; sync is paused and the data may be incomplete.${read}`;
    case "unknown_coverage": return `coverage unknown${row.covers_day === false ? "; selected day not covered" : ""}; no event here does not mean a free day.${read}`;
  }
}
export function limitNotes(briefing: Briefing): string[] {
  const limits = briefing.limits;
  if (!limits) return Object.entries(briefing.truncated).filter(([, flag]) => flag).map(([name]) => `More ${name} exist than this briefing can show.`);
  const notes: string[] = [];
  for (const [name, limit] of [["calendar sources", limits.sources], ["calendar occurrences", limits.events], ["tasks", limits.tasks], ["memory references", limits.memories]] as const) {
    if (limit.truncated) notes.push(`Showing ${limit.shown} ${name}; at least ${limit.omitted_at_least} more exist and are not shown.`);
  }
  if (limits.unreadable_items) notes.push(`${limits.unreadable_items} stored calendar item${limits.unreadable_items === 1 ? "" : "s"} could not be read; the agenda may be incomplete.`);
  return notes;
}
export function eventMarks(row: AgendaEvent): string {
  const marks: string[] = [];
  if (row.recurring) marks.push("recurring");
  if (row.exception === "modified") marks.push("changed instance");
  if (row.continues && row.days) marks.push(`continues across ${row.days.length} days`);
  if (row.possible_duplicate_of?.length) marks.push(`possible duplicate of ${row.possible_duplicate_of.length} other event${row.possible_duplicate_of.length === 1 ? "" : "s"} (not merged)`);
  return marks.join("; ");
}
