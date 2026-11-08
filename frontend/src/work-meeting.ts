import type { NotesArchive, ReferencedNote } from "./work-notes-api";

export type MeetingOptions = Readonly<{ title: string; starts_at: string | null }>;
export type DueRelation = "unknown_due" | "unknown_meeting" | "by_meeting" | "after_meeting";
export type MeetingNote = Readonly<{ reference: ReferencedNote; citation: string; label: string; owner: string; due_relation: DueRelation }>;
export type MeetingSection = Readonly<{ kind: ReferencedNote["item"]["kind"]; title: string; notes: MeetingNote[] }>;
export type MeetingBrief = Readonly<{ options: MeetingOptions; archive: NotesArchive; sections: MeetingSection[]; selected: MeetingNote[]; actions: { total: number; unknown_owner: number; unavailable_owner: number; unknown_due: number; by_meeting: number; after_meeting: number; unknown_meeting: number } }>;
export class MeetingError extends Error {}
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const label = /^[a-zA-Z0-9 _.-]{1,246}$/;
const kinds = [["action", "Actions and follow-ups"], ["decision", "Decisions"], ["question", "Questions"], ["observation", "Observations"]] as const;
function fail(): never { throw new MeetingError("This meeting snapshot could not be verified. Reload current notes."); }
function time(value: string): number { const result = Date.parse(value); if (!Number.isFinite(result) || !/(Z|[+-]\d\d:\d\d)$/.test(value)) return fail(); return result; }

export function meetingOptions(title: string, starts_at: string | null): MeetingOptions {
  const text = title.trim();
  if (!/^[a-zA-Z0-9 _.-]{1,120}$/.test(text)) throw new MeetingError("Use a sample meeting title of 1–120 letters, numbers, spaces, dots, underscores or hyphens.");
  if (starts_at !== null) time(starts_at);
  return Object.freeze({ title: text, starts_at: starts_at === null ? null : new Date(starts_at).toISOString() });
}

/** Arrange explicit confirmed snapshots only. Confirmation never implies completion. */
export function meetingBrief(archive: NotesArchive, options: MeetingOptions): MeetingBrief {
  const prepared = meetingOptions(options.title, options.starts_at);
  if (archive.schema_version !== 1 || archive.mode !== "synthetic_work_notes_archive" || !uuid.test(archive.workspace_id) || !uuid.test(archive.export_id) || archive.drafts_permitted !== false || archive.managed_copy !== false || archive.current_revisions_only !== true || archive.execution_allowed !== false || archive.raw_transcripts_included !== false || !archive.items.length || archive.items.length > 10 || new Set(archive.items.map(r => r.item.id)).size !== archive.items.length || time(archive.generated_at) >= time(archive.retain_until)) return fail();
  const selected = archive.items.map((reference, index): MeetingNote => {
    const { item, references } = reference;
    if (item.workspace_id !== archive.workspace_id || !uuid.test(item.id) || item.state !== "confirmed" || !Number.isInteger(item.revision) || item.revision < 1 || item.revision > 100 || !kinds.some(([kind]) => kind === item.kind) || !item.marker.startsWith("synthetic:") || !label.test(item.marker.slice(10)) || !item.source_ids.length || item.source_ids.length > 10 || new Set(item.source_ids).size !== item.source_ids.length || references.sources.length !== item.source_ids.length || new Set(references.sources.map(s => s.id)).size !== item.source_ids.length || !references.sources.every(s => uuid.test(s.id) && label.test(s.label) && item.source_ids.includes(s.id)) || time(item.retain_until) < time(archive.retain_until)) return fail();
    const owner = references.owner;
    if ((item.owner_id === null) !== (owner === null) || (owner && (owner.id !== item.owner_id || !uuid.test(owner.id) || typeof owner.available !== "boolean" || (owner.available ? owner.label === null || !label.test(owner.label) : owner.label !== null)))) return fail();
    if (item.due_at !== null) time(item.due_at);
    const due_relation: DueRelation = item.due_at === null ? "unknown_due" : prepared.starts_at === null ? "unknown_meeting" : time(item.due_at) <= time(prepared.starts_at) ? "by_meeting" : "after_meeting";
    return { reference, citation: `N${index + 1}`, label: item.marker.slice(10), owner: owner === null ? "Unknown" : owner.available ? owner.label! : "Previous owner unavailable", due_relation };
  });
  const actions = selected.filter(note => note.reference.item.kind === "action");
  return { options: prepared, archive, selected, sections: kinds.map(([kind, title]) => ({ kind, title, notes: selected.filter(note => note.reference.item.kind === kind) })), actions: { total: actions.length, unknown_owner: actions.filter(note => note.reference.item.owner_id === null).length, unavailable_owner: actions.filter(note => note.reference.references.owner?.available === false).length, unknown_due: actions.filter(note => note.due_relation === "unknown_due").length, by_meeting: actions.filter(note => note.due_relation === "by_meeting").length, after_meeting: actions.filter(note => note.due_relation === "after_meeting").length, unknown_meeting: actions.filter(note => note.due_relation === "unknown_meeting").length } };
}
