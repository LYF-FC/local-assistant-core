import type { NotesArchive, ReferencedNote } from "../work-notes-api";

export const workspace = "11111111-1111-4111-8111-111111111111";
const source = "22222222-2222-4222-8222-222222222222";
export function record(n: number, kind: ReferencedNote["item"]["kind"] = "action"): ReferencedNote {
  return { item: { id: `a0000000-0000-4000-8000-${String(n).padStart(12, "0")}`, workspace_id: workspace, policy_id: "44444444-4444-4444-8444-444444444444", revision: 2, state: "confirmed", actor_id: "55555555-5555-4555-8555-555555555555", created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-02T10:00:00Z", kind, marker: `synthetic:Sample note ${n}`, source_ids: [source], owner_id: null, due_at: null, retain_until: "2026-11-09T10:00:00Z" }, references: { sources: [{ id: source, label: "Sample source" }], owner: null, policy: { id: "44444444-4444-4444-8444-444444444444", max_age_seconds: 31536000 } } };
}
export function archive(items = [record(1)]): NotesArchive {
  return { schema_version: 1, mode: "synthetic_work_notes_archive", workspace_id: workspace, export_id: "66666666-6666-4666-8666-666666666666", generated_at: "2026-11-07T10:00:00Z", retain_until: "2026-11-08T10:00:00Z", current_revisions_only: true, managed_copy: false, execution_allowed: false, raw_transcripts_included: false, drafts_permitted: false, items };
}

