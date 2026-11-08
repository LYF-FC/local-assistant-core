import type { NotesArchive } from "./work-notes-api";
import { meetingBrief, meetingOptions, MeetingError } from "./work-meeting";
import type { MeetingNote } from "./work-meeting";

export type ReviewDue = "past" | "next7" | "later" | "unknown" | "not_action";
export type ReviewOptions = { title: string; as_of: string; query: string; kind: "all" | "action" | "decision" | "question" | "observation"; owner: string; source: string; due: "all" | Exclude<ReviewDue, "not_action">; activity: "all" | "created" | "updated"; from: string; until: string; sort: "selection" | "due" | "updated" };
export type ReviewNote = MeetingNote & { due: ReviewDue; created_in_window: boolean; updated_in_window: boolean };
export type WorkReview = { archive: NotesArchive; options: ReviewOptions; selected: ReviewNote[]; visible: ReviewNote[]; owners: { id: string; label: string; notes: ReviewNote[] }[]; counts: { actions: number; decisions: number; questions: number; observations: number; past: number; next7: number; unknown_owner: number; unknown_due: number; created: number; updated: number } };
const day = 86400000, uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const fail = (): never => { throw new MeetingError("Check the work review filters and UTC activity window (up to 366 days)."); };
function instant(value: string) { const result = Date.parse(value); if (!Number.isFinite(result) || !/(Z|[+-]\d\d:\d\d)$/.test(value)) return fail(); return result; }
export function defaultReviewOptions(at: string): ReviewOptions {
  const end = instant(at);
  return { title: "Sample work status report", as_of: new Date(end).toISOString(), query: "", kind: "all", owner: "all", source: "all", due: "all", activity: "all", from: new Date(end - 7 * day).toISOString(), until: new Date(end).toISOString(), sort: "selection" };
}
export function reviewOptions(value: ReviewOptions): ReviewOptions {
  const title = meetingOptions(value.title, null).title;
  if (typeof value.query !== "string" || value.query.length > 120 || /[\x00-\x1f\x7f]/.test(value.query) || !["all", "action", "decision", "question", "observation"].includes(value.kind) || !["all", "past", "next7", "later", "unknown"].includes(value.due) || !["all", "created", "updated"].includes(value.activity) || !["selection", "due", "updated"].includes(value.sort) || !(value.owner === "all" || value.owner === "unknown" || value.owner === "unavailable" || uuid.test(value.owner)) || !(value.source === "all" || uuid.test(value.source))) return fail();
  const from = instant(value.from), until = instant(value.until); instant(value.as_of);
  if (from >= until || until - from > 366 * day) return fail();
  return { ...value, title, as_of: new Date(value.as_of).toISOString(), query: value.query.trim(), owner: value.owner.toLowerCase(), source: value.source.toLowerCase(), from: new Date(from).toISOString(), until: new Date(until).toISOString() };
}
/** Only explicitly selected current confirmed records. No completion or event-history inference. */
export function workReview(archive: NotesArchive, input: ReviewOptions): WorkReview {
  const options = reviewOptions(input), base = meetingBrief(archive, { title: options.title, starts_at: null });
  const asOf = instant(options.as_of), from = instant(options.from), until = instant(options.until);
  if (asOf > instant(archive.generated_at)) return fail();
  const inside = (value: string) => instant(value) >= from && instant(value) < until;
  const selected: ReviewNote[] = base.selected.map(note => {
    const item = note.reference.item, created = instant(item.created_at), updated = instant(item.updated_at);
    if (created > updated || updated > asOf) return fail();
    const due: ReviewDue = item.kind !== "action" ? "not_action" : item.due_at === null ? "unknown" : instant(item.due_at) < asOf ? "past" : instant(item.due_at) < asOf + 7 * day ? "next7" : "later";
    return { ...note, due, created_in_window: inside(item.created_at), updated_in_window: inside(item.updated_at) };
  });
  // Valid facet IDs must come from this exact snapshot; labels alone never grant a match.
  if (uuid.test(options.owner) && !selected.some(n => n.reference.item.owner_id?.toLowerCase() === options.owner)) return fail();
  if (uuid.test(options.source) && !selected.some(n => n.reference.item.source_ids.some(id => id.toLowerCase() === options.source))) return fail();
  const visible = selected.filter(note => {
    const { item, references } = note.reference;
    const ownerMatch = options.owner === "all" || (options.owner === "unknown" ? item.owner_id === null : options.owner === "unavailable" ? references.owner?.available === false : item.owner_id?.toLowerCase() === options.owner);
    const text = [note.label, note.owner, item.id, ...references.sources.map(s => s.label)].join(" ").toLowerCase();
    return text.includes(options.query.toLowerCase()) && (options.kind === "all" || item.kind === options.kind) && ownerMatch && (options.source === "all" || item.source_ids.some(id => id.toLowerCase() === options.source)) && (options.due === "all" || note.due === options.due) && (options.activity === "all" || (options.activity === "created" ? note.created_in_window : note.updated_in_window));
  });
  if (options.sort === "due") visible.sort((a, b) => (a.reference.item.due_at === null ? Infinity : instant(a.reference.item.due_at)) - (b.reference.item.due_at === null ? Infinity : instant(b.reference.item.due_at)));
  if (options.sort === "updated") visible.sort((a, b) => instant(b.reference.item.updated_at) - instant(a.reference.item.updated_at));
  const groups = new Map<string, { id: string; label: string; notes: ReviewNote[] }>();
  for (const note of visible) { const id = note.reference.item.owner_id ?? "unknown"; if (!groups.has(id)) groups.set(id, { id, label: note.owner, notes: [] }); groups.get(id)!.notes.push(note); }
  const count = (predicate: (note: ReviewNote) => boolean) => visible.filter(predicate).length;
  return { archive, options, selected, visible, owners: [...groups.values()], counts: { actions: count(n => n.reference.item.kind === "action"), decisions: count(n => n.reference.item.kind === "decision"), questions: count(n => n.reference.item.kind === "question"), observations: count(n => n.reference.item.kind === "observation"), past: count(n => n.due === "past"), next7: count(n => n.due === "next7"), unknown_owner: count(n => n.reference.item.owner_id === null), unknown_due: count(n => n.reference.item.kind === "action" && n.reference.item.due_at === null), created: count(n => n.created_in_window), updated: count(n => n.updated_in_window) } };
}
export const reviewDueLabel: Record<ReviewDue, string> = { past: "Past due date - completion Unknown", next7: "Due in next 7 days - completion Unknown", later: "Due later - completion Unknown", unknown: "Due date Unknown - completion Unknown", not_action: "Not an action" };
