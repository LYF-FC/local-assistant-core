import type { NotesArchive } from "./work-notes-api";
import { markdownText } from "./work-meeting-markdown";
import { MeetingError } from "./work-meeting";
import { reviewDueLabel, workReview } from "./work-review";
import type { ReviewOptions } from "./work-review";

export function reviewMarkdown(archive: NotesArchive, options: ReviewOptions): { text: string; bytes: number; filename: string } {
  const review = workReview(archive, options), { counts: c, options: o } = review;
  if (!review.visible.length) throw new MeetingError("No notes match this report. Change the review filters.");
  const lines = ["# Selected work status report", "", `Title: ${markdownText(o.title)}`, `Reviewed reference time: ${o.as_of}`, `Fresh export prepared: ${new Date(archive.generated_at).toISOString()}`, `Workspace: \`${archive.workspace_id}\``, `Export reference: \`${archive.export_id}\``, `Copy retention ends: ${new Date(archive.retain_until).toISOString()}`, `Coverage: ${review.visible.length} visible of ${review.selected.length} explicitly selected confirmed notes. This is not a complete workspace inventory.`, "", "Filters and title are browser annotations, not server-signed business records. Current record timestamps are not event history or proof of net progress.", "Completion is Unknown. Confirmation is not action completion; a past due date is not proof that work is incomplete.", "This is an unmanaged separate copy. Butler cannot erase it after forgetting, source withdrawal or expiry. Delete it by the earliest selected retention boundary.", "", "## Review scope", "", `Text query: ${o.query ? markdownText(o.query) : "None"}`, `Kind: ${o.kind}`, `Owner filter: ${o.owner}`, `Source filter: ${o.source}`, `Action due filter: ${o.due}`, `Activity filter: ${o.activity}`, `Activity window (UTC, start inclusive/end exclusive): ${o.from} to ${o.until}`, `Order: ${o.sort}`, "", "## Visible summary", "", `Actions: ${c.actions}; decisions: ${c.decisions}; questions: ${c.questions}; observations: ${c.observations}.`, `Action dates before snapshot: ${c.past}; due in next 7 days: ${c.next7}; due date Unknown: ${c.unknown_due}.`, `Owner Unknown: ${c.unknown_owner}. Completion: Unknown.`, `Current records created in window: ${c.created}; updated in window: ${c.updated}. These counts may overlap.`, "", "## Owner groups", ""];
  for (const group of review.owners) lines.push(`- ${markdownText(group.label)} (${group.id === "unknown" ? "Unknown" : `\`${group.id}\``}): ${group.notes.map(n => `[^${n.citation}]`).join(", ")}`);
  lines.push("", "## Reviewed notes", "");
  for (const note of review.visible) {
    const item = note.reference.item;
    lines.push(`- ${markdownText(note.label)} [^${note.citation}]`, `  - Kind: ${item.kind}; owner: ${markdownText(note.owner)}`, `  - Due: ${item.due_at === null ? "Unknown" : new Date(item.due_at).toISOString()}; ${reviewDueLabel[note.due]}`, `  - Created: ${new Date(item.created_at).toISOString()}; updated: ${new Date(item.updated_at).toISOString()}`, `  - Note retention ends: ${new Date(item.retain_until).toISOString()}`, "");
  }
  lines.push("## Sources and versions", "");
  for (const note of review.visible) {
    lines.push(`[^${note.citation}]: Note \`${note.reference.item.id}\`, version ${note.reference.item.revision}.`);
    for (const source of note.reference.references.sources) lines.push(`    - Source: ${markdownText(source.label)} (\`${source.id}\`)`);
    if (note.reference.item.owner_id) lines.push(`    - Owner reference: \`${note.reference.item.owner_id}\` (${note.reference.references.owner!.available ? "available" : "unavailable"})`);
    lines.push("");
  }
  const text = lines.join("\n"), bytes = new TextEncoder().encode(text).length;
  if (bytes > 65536) throw new MeetingError("The work report is too large. Select fewer notes.");
  return { text, bytes, filename: `butler-work-report-${archive.workspace_id}-${archive.export_id}.md` };
}
