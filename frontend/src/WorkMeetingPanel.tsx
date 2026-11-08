import { useState } from "react";
import type { ExportRequest, NoteRow, NotesExport } from "./work-notes-api";
import { meetingBrief, meetingOptions, MeetingError } from "./work-meeting";
import type { MeetingBrief, MeetingOptions } from "./work-meeting";

const date = (value: string) => new Date(value).toLocaleString();
export default function WorkMeetingPanel({ rows, busy, blocked, preview, onPrepare, onDownload, onInvalidate, onClose }: {
  rows: NoteRow[]; busy: boolean; blocked: boolean; preview: NotesExport | null;
  onPrepare: (request: ExportRequest) => void; onDownload: (options: MeetingOptions) => void; onInvalidate: () => void; onClose: () => void;
}) {
  const [open, setOpen] = useState(false), [title, setTitle] = useState("Sample meeting"), [when, setWhen] = useState("");
  const [selected, setSelected] = useState<NoteRow[]>([]), [options, setOptions] = useState<MeetingOptions | null>(null);
  const [acknowledged, setAcknowledged] = useState(false), [error, setError] = useState("");
  function invalidate() { setOptions(null); setAcknowledged(false); setError(""); onInvalidate(); }
  function prepare() {
    if (blocked || !selected.length) return;
    try {
      const configured = meetingOptions(title, when ? new Date(when).toISOString() : null);
      setOptions(configured); setAcknowledged(false); setError("");
      onPrepare({ selections: selected.map(note => ({ id: note.id, expected_revision: note.revision })), include_drafts: false, purpose: "preview" });
    } catch (err) { setError(err instanceof MeetingError ? err.message : "Check the sample meeting title and time."); }
  }
  let brief: MeetingBrief | null = null, snapshotError = "";
  if (preview && options) {
    try { brief = meetingBrief(preview.bundle, options); }
    catch { snapshotError = "The meeting snapshot could not be verified. Close it and reload current notes."; }
  }
  if (!open) return <button disabled={blocked} onClick={() => { onInvalidate(); setOpen(true); }}>Prepare a meeting</button>;
  return <section className="work-meeting" aria-label="Sample meeting workbench">
    <div className="work-meeting-heading"><div><p className="work-eyebrow">Selected notes · Meeting preparation</p><h4>Prepare a sample meeting</h4></div><span className="work-meeting-badge">Confirmed notes only</span></div>
    <p>Arrange confirmed sample notes into an agenda with cited decisions, questions and action follow-ups. Preparing a brief does not create tasks or send messages.</p>
    <fieldset disabled={blocked}>
      <div className="work-meeting-inputs"><label>Meeting title<input aria-label="Meeting title" value={title} maxLength={120} onChange={event => { setTitle(event.target.value); invalidate(); }} /></label><label>Meeting time (optional)<input type="datetime-local" aria-label="Meeting time (optional)" value={when} onChange={event => { setWhen(event.target.value); invalidate(); }} /></label></div>
      <p className="hint">Choose up to 10 confirmed notes from this page. Unknown meeting times, owners and due dates stay Unknown.</p>
      <div className="work-meeting-choices">{rows.filter(note => note.content_available && note.state === "confirmed" && note.revision <= 100).map(note => <label className="work-check" key={note.id}><input type="checkbox" aria-label={`Meeting note ${note.label}`} checked={selected.some(value => value.id === note.id)} disabled={selected.length >= 10 && !selected.some(value => value.id === note.id)} onChange={event => { setSelected(event.target.checked ? [...selected, note] : selected.filter(value => value.id !== note.id)); invalidate(); }} /><span>{note.label} <small>version {note.revision}</small></span></label>)}</div>
      {!rows.some(note => note.content_available && note.state === "confirmed") && <p>No confirmed notes on this page. Confirm a reviewed note first or load another page.</p>}
      <button disabled={!selected.length} onClick={prepare}>Preview meeting brief</button>
    </fieldset>
    {error && <p role="alert" className="error">{error}</p>}{snapshotError && <p role="alert" className="error">{snapshotError}</p>}
    {brief && <section aria-label="Reviewed meeting brief" className="work-meeting-preview">
      <header><p className="work-eyebrow">{brief.selected.length} selected note{brief.selected.length === 1 ? "" : "s"}</p><h5>{brief.options.title}</h5><p>Meeting time: {brief.options.starts_at ? date(brief.options.starts_at) : "Unknown"}</p><p className="hint">Snapshot valid until {date(preview!.valid_until)}. Completion is Unknown; a confirmed note does not mean an action is complete.</p></header>
      <section className="work-meeting-followups" aria-label="Selected action follow-ups"><h5>Selected action follow-ups</h5><dl><div><dt>Selected actions</dt><dd>{brief.actions.total}</dd></div><div><dt>Due by meeting</dt><dd>{brief.options.starts_at === null ? "Not assessed" : brief.actions.by_meeting}</dd></div><div><dt>Owner Unknown</dt><dd>{brief.actions.unknown_owner}</dd></div><div><dt>Owner unavailable</dt><dd>{brief.actions.unavailable_owner}</dd></div><div><dt>Due date Unknown</dt><dd>{brief.actions.unknown_due}</dd></div></dl></section>
      <div className="work-meeting-sections">{brief.sections.map(section => <section key={section.kind} aria-label={`Meeting ${section.title}`}><h5>{section.title}</h5>{section.notes.length ? <ol>{section.notes.map(note => <li key={note.reference.item.id}><strong>{note.label}</strong> <span className="work-meeting-citation">[{note.citation}]</span><p>Owner: {note.owner} · Due: {note.reference.item.due_at ? date(note.reference.item.due_at) : "Unknown"}</p>{section.kind === "action" && <p className="hint">{note.due_relation === "by_meeting" ? "Due by meeting" : note.due_relation === "after_meeting" ? "Due after meeting" : note.due_relation === "unknown_meeting" ? "Meeting time Unknown" : "Due date Unknown"} · Completion: Unknown</p>}</li>)}</ol> : <p className="hint">No selected notes in this section.</p>}</section>)}</div>
      <details className="work-meeting-sources"><summary>Sources and versions</summary><ol>{brief.selected.map(note => <li key={note.citation}><strong>[{note.citation}] {note.label}</strong><p>Note <code>{note.reference.item.id}</code> · version {note.reference.item.revision}</p><ul>{note.reference.references.sources.map(source => <li key={source.id}>{source.label} · <code>{source.id}</code></li>)}</ul><p>Note retention ends {date(note.reference.item.retain_until)}</p></li>)}</ol></details>
      <div className="work-meeting-copy"><h5>Keep a reviewed copy</h5><p>Copy retention ends {date(brief.archive.retain_until)}. A downloaded file is a separate copy; Butler cannot erase it when notes are forgotten or expire.</p>{brief.options.starts_at && Date.parse(brief.options.starts_at) >= Date.parse(brief.archive.retain_until) && <p role="status">The meeting time is at or after this copy's retention boundary. Refresh with eligible notes before the meeting.</p>}<label className="work-check"><input type="checkbox" disabled={blocked} checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />I will manage the meeting copy and its retention</label><button disabled={blocked || !acknowledged} onClick={() => onDownload(brief!.options)}>Download reviewed meeting Markdown</button><p className="hint">Download checks access and the exact reviewed notes again. Your meeting title and time stay browser annotations.</p></div>
    </section>}
    <button onClick={onClose}>{busy ? "Cancel meeting request" : "Close meeting workbench"}</button>
  </section>;
}
