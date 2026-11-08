import { useState } from "react";
import type { ExportRequest, NoteRow, NotesExport } from "./work-notes-api";

export default function WorkExportPanel({ rows, busy, blocked, preview, onPrepare, onDownload, onInvalidate, onClose }: {
  rows: NoteRow[]; busy: boolean; blocked: boolean; preview: NotesExport | null;
  onPrepare: (request: ExportRequest) => void; onDownload: () => void; onInvalidate: () => void; onClose: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState(false);
  const [selected, setSelected] = useState<NoteRow[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  function invalidate() { onInvalidate(); setAcknowledged(false); }
  if (!open) return <button disabled={blocked} onClick={() => { invalidate(); setOpen(true); }}>Export selected notes</button>;
  return <section aria-label="Selected Work export" className="work-export">
    <h4>Export selected sample notes</h4><p>Choose up to 10 notes from this page. Only current versions are included, with their source references and retention limits.</p>
    <fieldset disabled={blocked}>
      <label className="work-check"><input type="checkbox" checked={drafts} onChange={e => { setDrafts(e.target.checked); setSelected([]); invalidate(); }} />Include unconfirmed drafts</label>
      <div className="work-export-choices">{rows.filter(n => n.content_available && n.revision <= 100 && (drafts || n.state === "confirmed")).map(n => <label className="work-check" key={n.id}><input type="checkbox" aria-label={`Export ${n.label}`} checked={selected.some(v => v.id === n.id)} disabled={selected.length >= 10 && !selected.some(v => v.id === n.id)} onChange={e => { setSelected(e.target.checked ? [...selected, n] : selected.filter(v => v.id !== n.id)); invalidate(); }} />{n.label} · {n.state} · version {n.revision}</label>)}</div>
      {!rows.some(n => n.content_available && (drafts || n.state === "confirmed")) && <p>No eligible notes on this page. Drafts require the explicit option above.</p>}
      <button disabled={!selected.length} onClick={() => { invalidate(); onPrepare({ selections: selected.map(n => ({ id: n.id, expected_revision: n.revision })), include_drafts: drafts, purpose: "preview" }); }}>Preview selected export</button>
    </fieldset>
    {preview && <section aria-label="Reviewed export preview"><h5>{preview.bundle.items.length} selected note{preview.bundle.items.length === 1 ? "" : "s"} · {preview.bundle_bytes} bytes</h5>
      <p>Keep the downloaded copy no later than {new Date(preview.bundle.retain_until).toLocaleString()}.</p>
      <ul>{preview.bundle.items.map(({ item, references }) => <li key={item.id}><strong>{item.marker.slice(10)}</strong><p>{item.kind} · {item.state} · version {item.revision}</p><p>Sources: {references.sources.map(s => s.label).join(", ")}</p><p>Owner: {references.owner?.label ?? (item.owner_id ? "Previous owner unavailable" : "Unknown")} · Due: {item.due_at ? new Date(item.due_at).toLocaleString() : "Unknown"}</p><p>Note expiry: {new Date(item.retain_until).toLocaleString()}</p></li>)}</ul>
      <p>A downloaded file is a separate copy. Butler cannot erase it when a note is forgotten or its retention ends. Older backups may also retain it.</p>
      <label className="work-check"><input type="checkbox" disabled={blocked} checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />I will manage the downloaded copy and its retention</label>
      <button disabled={blocked || !acknowledged} onClick={onDownload}>Download reviewed JSON</button>
      <p className="hint">Downloading rechecks access and the exact reviewed contents. The receipt records preparation, not proof that a file was saved or deleted.</p>
    </section>}
    <button onClick={onClose}>{busy ? "Cancel export request" : "Close export"}</button>
  </section>;
}
