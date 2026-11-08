import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Session } from "./api";
import { suggestedTitle } from "./capture";
import { ContentView } from "./MemoryContent";
import { MemoryError, correctMemory, createMemory, exportMemory, forgetMemory, historyMemory, listMemory, memoryKinds, memoryScopes, readMemory } from "./memory-api";
import type { ActiveMemory, Entry, Filters, History, Kind, Page, Scope, Values } from "./memory-api";

const dateLabel = (value: string) => new Date(value).toLocaleString();
const title = (entry: Entry) => entry.state === "active" ? entry.title : "Forgotten entry";

function localDate(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function Editor({ entry, scopes, busy, conflict, onSave, onCancel }: { entry: ActiveMemory | null; scopes: Scope[]; busy: boolean; conflict: boolean; onSave: (values: Values, scope: Scope, kind: Kind) => void; onCancel: () => void }) {
  const [heading, setHeading] = useState<string | null>(entry?.title ?? null);
  const textEntry = !entry || (Object.keys(entry.content).length === 1 && typeof entry.content.text === "string");
  const [details, setDetails] = useState(entry && textEntry ? String(entry.content.text) : "");
  const [scope, setScope] = useState<Scope>(entry?.scope ?? scopes[0]);
  const [kind, setKind] = useState<Kind>(entry?.kind ?? "preference");
  const [sourceType, setSourceType] = useState<Values["source_type"]>(entry?.source_type ?? "manual");
  const [source, setSource] = useState(entry?.source_reference ?? "Manually entered");
  const [assessment, setAssessment] = useState<Values["assessment"]>(entry?.assessment ?? "tentative");
  const [expiry, setExpiry] = useState(localDate(entry?.expires_at ?? null));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || conflict) return;
    onSave({ title: (heading ?? suggestedTitle(details)).trim(), content: textEntry ? { text: details } : entry!.content, source_type: sourceType, source_reference: source.trim(), assessment, expires_at: expiry ? new Date(expiry).toISOString() : null }, scope, kind);
  }
  return <form className="memory-editor" aria-label={entry ? "Edit memory" : "New memory"} onSubmit={submit}>
    <h3>{entry ? "Correct this entry" : "Add something to remember"}</h3>
    <fieldset disabled={busy || conflict}>
      <label>Title<input value={heading ?? suggestedTitle(details)} onChange={e => setHeading(e.target.value)} maxLength={160} required /></label>
      {textEntry ? <label>Details<textarea aria-label="Details" value={details} onChange={e => setDetails(e.target.value)} maxLength={4000} required rows={5} /></label> : <div><p>These details are maintained by their source feature and will be preserved.</p><ContentView value={entry!.content} /></div>}
      <label>Access<select aria-label="Access" value={scope} onChange={e => setScope(e.target.value as Scope)} disabled={!!entry}>{scopes.map(value => <option key={value} value={value}>{memoryScopes[value]}</option>)}</select></label>
      <label>Entry type<select aria-label="Entry type" value={kind} onChange={e => setKind(e.target.value as Kind)} disabled={!!entry}>{Object.entries(memoryKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      {!entry && <p className="hint">The title starts from your first nonblank line and stays editable. New entries are {assessment === "tentative" ? "Tentative" : "Confirmed by your choice"}. Source: {sourceType} · {source}. No verification is inferred.</p>}
      <details open={!!entry} className="capture-details"><summary>Source, assessment and optional details</summary>
      <label>Source type<select aria-label="Source type" value={sourceType} onChange={e => setSourceType(e.target.value as Values["source_type"])}><option value="manual">Manual note</option><option value="document">Document</option><option value="conversation">Conversation</option><option value="feedback">Feedback</option></select></label>
      <label>Source or reference<input value={source} onChange={e => setSource(e.target.value)} maxLength={512} required /></label>
      <label>Assessment<select aria-label="Assessment" value={assessment} onChange={e => setAssessment(e.target.value as Values["assessment"])}><option value="confirmed">Confirmed</option><option value="tentative">Tentative</option></select></label>
      </details>
      {kind === "context" ? <label>Expires at (your local time)<input aria-label="Expires at (your local time)" type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)} required /></label> : <details className="capture-details" open={!!entry && !!expiry}><summary>Optional expiry</summary><label>Expires at (your local time)<input aria-label="Expires at (your local time)" type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)} /></label></details>}
      <button type="submit">{busy ? "Saving…" : "Save entry"}</button>
    </fieldset>
    {conflict && <p>Your draft has been kept. Close it and reload the entry to review the latest version.</p>}
    <button type="button" disabled={busy} onClick={onCancel}>{conflict ? "Discard draft and reload" : "Cancel editing"}</button>
  </form>;
}
function ForgetDialog({ entry, busy, error, onConfirm, onCancel }: { entry: ActiveMemory; busy: boolean; error: string; onConfirm: () => void; onCancel: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current!; dialog.showModal(); return () => dialog.close(); }, []);
  return <dialog ref={ref} aria-labelledby="forget-heading" onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h3 id="forget-heading">Forget this memory?</h3><p>{entry.title}</p>
    <p>This removes the entry and all saved revisions from live memory. Existing exports and older backups can retain copies.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="memory-actions"><button disabled={busy} onClick={onCancel}>Keep entry</button><button className="danger" disabled={busy} onClick={onConfirm}>{busy ? "Forgetting…" : "Forget permanently from live memory"}</button></div>
  </dialog>;
}
export default function MemoryPanel({ session, onUnauthorized }: { session: Session; onUnauthorized: () => void }) {
  const scopes = session.user.scopes.filter((value): value is Scope => Object.hasOwn(memoryScopes, value));
  const [filters, setFilters] = useState<Filters>({ scope: "", kind: "", expired: false, forgotten: false });
  const [previous, setPrevious] = useState<(string | undefined)[]>([]);
  const [page, setPage] = useState<Page | null>(null);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [editing, setEditing] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [confirm, setConfirm] = useState<ActiveMemory | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const controllers = useRef(new Set<AbortController>());
  useEffect(() => () => { controllers.current.forEach(controller => controller.abort()); controllers.current.clear(); }, []);
  function clearPayload() { setPage(null); setSelected(null); setHistory(null); setEditing(false); setConfirm(null); }
  function invalidatePayload() {
    controllers.current.forEach(controller => controller.abort()); controllers.current.clear();
    clearPayload(); setBusy(false); setLoading(false);
  }
  function failure(err: unknown) {
    if (err instanceof MemoryError && err.status === 409) { setConflict(true); setError(err.message); return; }
    if (err instanceof MemoryError && ![401, 403, 404, 410].includes(err.status)) { setError(err.message); return; }
    invalidatePayload();
    setError(err instanceof MemoryError ? err.message : "Memory is unavailable. Try again.");
    if (err instanceof MemoryError && err.status === 401) onUnauthorized();
  }
  useEffect(() => {
    const controller = new AbortController(); controllers.current.add(controller);
    setLoading(true); setPage(null);
    listMemory(filters, controller.signal).then(value => { if (!controller.signal.aborted) setPage(value); }).catch(err => { if (!controller.signal.aborted) failure(err); }).finally(() => { controllers.current.delete(controller); if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filters, reload]);
  async function action<T>(work: (signal: AbortSignal) => Promise<T>, success: (value: T) => void) {
    if (busy) return;
    const controller = new AbortController(); controllers.current.add(controller);
    setBusy(true); setError(""); setMessage("");
    try { const value = await work(controller.signal); if (!controller.signal.aborted) success(value); }
    catch (err) { if (!controller.signal.aborted) failure(err); }
    finally { controllers.current.delete(controller); if (!controller.signal.aborted) setBusy(false); }
  }
  function resetSelection() { setSelected(null); setHistory(null); setEditing(false); setConflict(false); setError(""); setMessage(""); }
  function filter(change: Partial<Filters>) { resetSelection(); setPrevious([]); setFilters({ ...filters, ...change, after: undefined }); }
  function select(entry: Entry) {
    resetSelection();
    if (entry.state === "forgotten") { setSelected(entry); return; }
    void action(signal => readMemory(entry.id, filters.expired, signal), value => setSelected(value));
  }
  function save(values: Values, scope: Scope, kind: Kind) {
    const entry = selected?.state === "active" ? selected : null;
    void action(signal => entry ? correctMemory(entry, values, session.csrfToken, signal) : createMemory(values, scope, kind, session.csrfToken, signal), value => { setSelected(value); setEditing(false); setConflict(false); setHistory(null); setMessage("Entry saved."); setReload(v => v + 1); });
  }
  function download() {
    void action(signal => exportMemory(filters, signal), value => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = "butler-memory-page.json"; document.body.append(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000); setMessage("Current page downloaded.");
    });
  }
  const owned = selected?.owner_id === session.user.id;
  return <section aria-label="Memory" className="memory-panel">
    <div className="section-heading"><div><p className="eyebrow">Your local records</p><h2>Memory</h2><p>Inspect what Butler remembers and keep its sources and details accurate.</p></div><button disabled={busy || editing || !scopes.length} onClick={() => { resetSelection(); setEditing(true); }}>Add memory</button></div>
    <div className="memory-filters">
      <label>Filter access<select aria-label="Filter access" disabled={busy || editing} value={filters.scope} onChange={e => filter({ scope: e.target.value })}><option value="">All my access</option>{scopes.map(scope => <option key={scope} value={scope}>{memoryScopes[scope]}</option>)}</select></label>
      <label>Filter type<select aria-label="Filter type" disabled={busy || editing} value={filters.kind} onChange={e => filter({ kind: e.target.value })}><option value="">All entry types</option>{Object.entries(memoryKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="check"><input type="checkbox" disabled={busy || editing} checked={filters.expired} onChange={e => filter({ expired: e.target.checked })} />Include my expired entries</label>
      <label className="check"><input type="checkbox" disabled={busy || editing} checked={filters.forgotten} onChange={e => filter({ forgotten: e.target.checked })} />Include my forgotten entries</label>
    </div>
    <div className="memory-actions"><button disabled={busy || editing || loading} onClick={() => { resetSelection(); setReload(v => v + 1); }}>Refresh list</button><button disabled={busy || editing || loading || !page?.items.length} onClick={download}>Download this page</button><span className="hint">Private JSON · up to 25 entries · current filters</span></div>
    {busy && !confirm && <p role="status">Working…</p>}
    {error && !confirm && <p role="alert" className="error">{error}</p>}{message && <p role="status">{message}</p>}
    <div className="memory-layout"><div>
      {loading ? <p role="status">Loading memory…</p> : page?.items.length === 0 ? <p>No entries match these filters.</p> : <ul className="memory-list">{page?.items.map(entry => <li key={entry.id}><button disabled={busy || editing} onClick={() => select(entry)} aria-pressed={selected?.id === entry.id}><strong>{title(entry)}</strong><span>{memoryKinds[entry.kind]} · {memoryScopes[entry.scope]}{entry.state === "active" && entry.expired ? " · Expired" : ""}</span></button></li>)}</ul>}
      <nav aria-label="Memory pages" className="memory-actions"><button disabled={busy || editing || loading || previous.length === 0} onClick={() => { resetSelection(); const next = [...previous]; const after = next.pop(); setPrevious(next); setFilters({ ...filters, after }); }}>Previous page</button><button disabled={busy || editing || loading || !page?.next_cursor} onClick={() => { resetSelection(); setPrevious([...previous, filters.after]); setFilters({ ...filters, after: page!.next_cursor! }); }}>Next page</button></nav>
    </div><div>
      {editing ? <Editor key={selected?.id ?? "new"} entry={selected?.state === "active" ? selected : null} scopes={scopes} busy={busy} conflict={conflict} onSave={save} onCancel={() => { const entry = selected; const reloadEntry = conflict; setEditing(false); setConflict(false); setError(""); if (reloadEntry && entry?.state === "active") { setSelected(null); setHistory(null); void action(signal => readMemory(entry.id, filters.expired, signal), setSelected); } }} /> : selected && <article aria-label="Memory details" className="memory-detail">
        <h3>{title(selected)}</h3><p>{memoryScopes[selected.scope]} · {memoryKinds[selected.kind]} · Revision {selected.revision}</p>
        {selected.state === "active" ? <><ContentView value={selected.content} /><dl><div><dt>Assessment</dt><dd>{selected.assessment === "confirmed" ? "Confirmed" : "Tentative"}</dd></div><div><dt>Source</dt><dd className="memory-text">{selected.source_reference} ({selected.source_type})</dd></div><div><dt>Updated</dt><dd>{dateLabel(selected.updated_at)}</dd></div>{selected.expires_at && <div><dt>Expires</dt><dd>{dateLabel(selected.expires_at)}{selected.expired ? " — expired, excluded from current context" : ""}</dd></div>}</dl>
          {owned && <div className="memory-actions"><button disabled={busy} onClick={() => { setHistory(null); setEditing(true); setConflict(false); setError(""); }}>Edit entry</button><button disabled={busy} onClick={() => { void action(signal => historyMemory(selected.id, 0, signal), setHistory); }}>View history</button><button className="danger" disabled={busy} onClick={() => { setError(""); setConfirm(selected); }}>Forget entry</button></div>}
          {!owned && <p className="hint">Shared with you. Only its owner can edit, inspect history or forget it.</p>}
        </> : <p>Live content and saved revisions have been removed.</p>}
      </article>}
      {history && selected && <section aria-label="Memory history" className="memory-detail"><h3>History — oldest first</h3><p>Saved snapshots are read-only and do not replace current context.</p>{history.items.map(row => <article key={row.revision}><h4>Revision {row.revision}{row.historical ? " — historical" : " — current"}</h4><p className="hint">{dateLabel(row.created_at)}</p>{row.snapshot ? <><strong>{row.snapshot.title}</strong><ContentView value={row.snapshot.content} /><p className="memory-text">Source: {row.snapshot.source_reference}</p></> : <p>Content forgotten.</p>}</article>)}{history.next_cursor && <button disabled={busy} onClick={() => { void action(signal => historyMemory(selected.id, history.next_cursor!, signal), setHistory); }}>Next history page</button>}</section>}
    </div></div>
    {confirm && <ForgetDialog entry={confirm} busy={busy} error={error} onCancel={() => { setConfirm(null); setError(""); }} onConfirm={() => { void action(signal => forgetMemory(confirm, session.csrfToken, signal), () => { invalidatePayload(); setConflict(false); setMessage("Memory forgotten from live records and saved revisions."); setReload(v => v + 1); }); }} />}
  </section>;
}
