import type { NotesArchive } from "./work-notes-api";
import { meetingBrief, MeetingError } from "./work-meeting";
import type { MeetingOptions } from "./work-meeting";

/** No dynamic HTML, links or Markdown syntax; citation labels and UUID code spans are generated. */
export function markdownText(value: string): string {
  return [...value].map(character => "\\`*_{}[]()#+-.!|~<>".includes(character) ? `\\${character}` : character).join("");
}
const iso = (value: string) => new Date(value).toISOString();
export function meetingMarkdown(archive: NotesArchive, options: MeetingOptions): { text: string; bytes: number; filename: string } {
  const brief = meetingBrief(archive, options), { actions } = brief;
  const lines = ["# Sample meeting brief", "", `Title: ${markdownText(brief.options.title)}`, `Meeting time: ${brief.options.starts_at ?? "Unknown"}`, `Prepared from current notes: ${iso(archive.generated_at)}`, `Workspace: \`${archive.workspace_id}\``, `Export reference: \`${archive.export_id}\``, `Copy retention ends: ${iso(archive.retain_until)}`, "", "This is a user-managed copy of selected synthetic notes. Butler cannot erase this file after forgetting or expiry.", "Meeting title and time are your annotations. Completion is Unknown; confirmation of a note is not completion of an action.", ""];
  if (brief.options.starts_at !== null && Date.parse(brief.options.starts_at) >= Date.parse(archive.retain_until)) lines.push("The meeting time is at or after this copy's retention boundary. Refresh with eligible notes before the meeting.", "");
  lines.push("## Selected action follow-ups", "", `Selected actions: ${actions.total}`, `Owner unknown: ${actions.unknown_owner}`, `Previous owner unavailable: ${actions.unavailable_owner}`, `Due date unknown: ${actions.unknown_due}`, `Due by meeting: ${brief.options.starts_at === null ? "Not assessed - meeting time Unknown" : actions.by_meeting}`, `Due after meeting: ${brief.options.starts_at === null ? "Not assessed - meeting time Unknown" : actions.after_meeting}`, "Completion: Unknown", "");
  for (const section of brief.sections) {
    lines.push(`## ${section.title}`, "");
    if (!section.notes.length) lines.push("No selected notes in this section.", "");
    for (const note of section.notes) {
      const item = note.reference.item;
      lines.push(`- ${markdownText(note.label)} [^${note.citation}]`, `  - Owner: ${markdownText(note.owner)}`, `  - Due date: ${item.due_at === null ? "Unknown" : iso(item.due_at)}`, `  - Note retention ends: ${iso(item.retain_until)}`);
      if (section.kind === "action") lines.push(`  - Due comparison: ${note.due_relation === "unknown_due" ? "Unknown due date" : note.due_relation === "unknown_meeting" ? "Meeting time Unknown" : note.due_relation === "by_meeting" ? "Due by meeting" : "Due after meeting"}`, "  - Completion: Unknown");
      lines.push("");
    }
  }
  lines.push("## Sources and versions", "");
  for (const note of brief.selected) {
    lines.push(`[^${note.citation}]: Note \`${note.reference.item.id}\`, version ${note.reference.item.revision}.`);
    for (const source of note.reference.references.sources) lines.push(`    - Source: ${markdownText(source.label)} (\`${source.id}\`)`);
    const owner = note.reference.references.owner;
    if (owner) lines.push(`    - Owner reference: \`${owner.id}\` (${owner.available ? "available" : "unavailable"})`);
    lines.push("");
  }
  const text = lines.join("\n"), bytes = new TextEncoder().encode(text).length;
  if (bytes > 65536) throw new MeetingError("The meeting brief is too large. Select fewer notes.");
  return { text, bytes, filename: `butler-work-meeting-${archive.workspace_id}-${archive.export_id}.md` };
}
