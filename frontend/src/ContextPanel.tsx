import { useEffect, useRef, useState } from "react";
import type { Session } from "./api";
import { buildPreview, ContextError, listCandidates } from "./context-api";
import type { Candidate, Candidates, Preview, Selection } from "./context-api";
import { ContentView } from "./MemoryContent";
import { memoryKinds, memoryScopes } from "./memory-api";
import type { Scope } from "./memory-api";

export default function ContextPanel({ session, onUnauthorized }: { session: Session; onUnauthorized: () => void }) {
  const scopes = session.user.scopes.filter((s): s is Scope => Object.hasOwn(memoryScopes, s));
  const [scope, setScope] = useState<Scope | "">(""); const [page, setPage] = useState<Candidates | null>(null);
  const [after, setAfter] = useState<string>(); const [previous, setPrevious] = useState<(string | undefined)[]>([]);
  const [selected, setSelected] = useState<Selection[]>([]); const [budget, setBudget] = useState(8192);
  const [bundle, setBundle] = useState<Preview | null>(null); const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const requests = useRef(new Set<AbortController>()); const previewRequest = useRef<AbortController | null>(null);
  useEffect(() => () => { requests.current.forEach(c => c.abort()); requests.current.clear(); }, []);
  useEffect(() => {
    if (!bundle) return;
    const timer = window.setTimeout(() => { setBundle(null); setMessage("Preview expired and cleared. Build again to recheck current records."); }, Math.min(60000, Math.max(0, Date.parse(bundle.valid_until) - Date.now())));
    return () => window.clearTimeout(timer);
  }, [bundle]);
  function clearPreview() { previewRequest.current?.abort(); setBusy(false); setBundle(null); setMessage(""); }
  function clearSelection() { clearPreview(); setSelected([]); setError(""); }
  function invalidate() { requests.current.forEach(c => c.abort()); requests.current.clear(); clearSelection(); setPage(null); setLoading(false); }
  function failure(err: unknown) {
    if (!(err instanceof ContextError) || [401, 403, 404, 409, 410, 422].includes(err.status)) {
      invalidate(); if (err instanceof ContextError && err.status === 401) onUnauthorized();
    }
    setError(err instanceof ContextError ? err.message : "Context is unavailable. Refresh the candidates.");
  }
  useEffect(() => {
    if (!scope) return;
    const controller = new AbortController(); requests.current.add(controller); setLoading(true); setPage(null);
    listCandidates(scope, after, controller.signal).then(value => { if (!controller.signal.aborted) setPage(value); }).catch(err => { if (!controller.signal.aborted) failure(err); }).finally(() => { requests.current.delete(controller); if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [scope, after, reload]);
  function choose(entry: Candidate, checked: boolean) {
    clearPreview(); setError("");
    setSelected(old => checked ? old.length < 10 ? [...old, { id: entry.id, expected_revision: entry.revision }] : old : old.filter(s => s.id !== entry.id));
  }
  async function preview() {
    if (!scope || busy || !selected.length) return;
    clearPreview(); setError(""); const controller = new AbortController(); previewRequest.current = controller; requests.current.add(controller); setBusy(true);
    try { const value = await buildPreview(scope, selected, budget, session.csrfToken, controller.signal); if (!controller.signal.aborted) setBundle(value); }
    catch (err) { if (!controller.signal.aborted) failure(err); }
    finally { requests.current.delete(controller); if (previewRequest.current === controller) previewRequest.current = null; if (!controller.signal.aborted) setBusy(false); }
  }
  return <section aria-label="Context preview" className="memory-panel"><p className="eyebrow">Local reference preview</p><h2>Choose what Butler could use</h2>
    <p>Select confirmed current records within one scope to inspect their content and sources. This preview does not call a model or authorize actions.</p>
    <div className="memory-filters"><label>Context scope<select aria-label="Context scope" value={scope} disabled={busy} onChange={e => { invalidate(); setScope(e.target.value as Scope | ""); setAfter(undefined); setPrevious([]); }}><option value="">Choose one scope</option>{scopes.map(s => <option key={s} value={s}>{memoryScopes[s]}</option>)}</select></label>
      <label>Items byte budget<select aria-label="Items byte budget" value={budget} disabled={busy} onChange={e => { clearPreview(); setError(""); setBudget(Number(e.target.value)); }}><option value={2048}>2 KiB</option><option value={4096}>4 KiB</option><option value={8192}>8 KiB</option><option value={16384}>16 KiB</option></select></label>
    </div>
    <p className="hint">Choose up to 10 records from this page. Tentative, expired, experience and module proposal records are excluded. Previews clear within 60 seconds; future use must check authority again.</p>
    <div className="memory-actions"><button disabled={!scope || busy || loading} onClick={() => { invalidate(); setReload(v => v + 1); }}>Refresh candidates</button><button disabled={busy || loading || !selected.length} onClick={() => { void preview(); }}>{busy ? "Building preview…" : "Build preview"}</button><button disabled={!selected.length && !bundle && !busy} onClick={clearSelection}>Clear selection and preview</button><span>{selected.length} of 10 selected</span></div>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status">{message}</p>}
    {!scope ? <p>Choose an assigned scope to load eligible records.</p> : loading ? <p role="status">Loading candidates…</p> : page?.items.length === 0 ? <p>No eligible records in this scope. Use Memory to inspect other entries.</p> : <ul className="context-candidates">{page?.items.map(entry => <li key={entry.id}><label className="context-choice"><input type="checkbox" aria-label={`Select ${entry.title}`} checked={selected.some(s => s.id === entry.id)} disabled={busy || (selected.length >= 10 && !selected.some(s => s.id === entry.id))} onChange={e => choose(entry, e.target.checked)} /><span><strong>{entry.title}</strong><span className="hint">{memoryKinds[entry.kind]} · Revision {entry.revision}</span><span className="memory-text">Source: {entry.source_reference} ({entry.source_type})</span>{entry.expires_at && <span className="hint">Expires: {new Date(entry.expires_at).toLocaleString()}</span>}</span></label></li>)}</ul>}
    <nav aria-label="Context candidate pages" className="memory-actions"><button disabled={busy || loading || !previous.length} onClick={() => { clearSelection(); const old = [...previous]; setAfter(old.pop()); setPrevious(old); }}>Previous candidates</button><button disabled={busy || loading || !page?.next_cursor} onClick={() => { clearSelection(); setPrevious([...previous, after]); setAfter(page!.next_cursor!); }}>Next candidates</button></nav>
    {bundle && <section aria-label="Built context preview" className="memory-detail"><h3>Reference preview</h3><p>{memoryScopes[bundle.scope]} · {bundle.items_bytes} of {bundle.max_bytes} items bytes · Clears by {new Date(bundle.valid_until).toLocaleTimeString()}</p><p className="hint">A snapshot of the selected revisions, not a reusable permission or approval. Text stays reference data, including text that resembles instructions.</p>
      {bundle.items.map(entry => <article key={entry.id}><h4>{entry.title}</h4><p className="hint">{memoryKinds[entry.kind]} · Confirmed · Revision {entry.revision}</p><ContentView value={entry.content} /><p className="memory-text">Source: {entry.source_reference} ({entry.source_type})</p><p className="hint">Record {entry.id} · Updated {new Date(entry.updated_at).toLocaleString()}</p></article>)}
    </section>}
  </section>;
}
