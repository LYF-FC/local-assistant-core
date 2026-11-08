import { useEffect, useRef, useState } from "react";
import DiscoveryDigestPanel from "./DiscoveryDigestPanel";
import { prepareDigest, DigestError } from "./discovery-digest-api";
import type { DigestRequest, DigestReview } from "./discovery-digest-api";
import { digestMarkdown } from "./discovery-digest";
import { IdeaCapture, ProposalCapture } from "./DiscoveryCapture";
import type { FormEvent } from "react";
import type { Session } from "./api";
import { choices, createIdea, createProposal, isIdea, saveProposalDetails, searchProposals, emptyInboxFilters, readProposal, saveFeedback } from "./discovery-api";
import type { Choice, Cursor, InboxFilters, Proposal, ProposalInput, Proposals } from "./discovery-api";
import { MemoryError, memoryScopes } from "./memory-api";

function FeedbackForm({ entry, busy, conflict, onChange, onSave, onReload }: { entry: Proposal; busy: boolean; conflict: boolean; onChange: () => void; onSave: (choice: Choice | null, note: string) => void; onReload: () => void }) {
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); onSave((data.get("choice") || null) as Choice | null, String(data.get("note") ?? "")); }
  return <form className="discovery-feedback" aria-label="Discovery feedback" onSubmit={submit} onChange={onChange}><fieldset disabled={busy || conflict}>
    <label>Your interest<select aria-label="Your interest" name="choice" defaultValue={entry.content.feedback?.choice ?? ""}><option value="">No current feedback</option>{Object.entries(choices).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label>Feedback note<textarea aria-label="Feedback note" name="note" defaultValue={entry.content.feedback?.note ?? ""} maxLength={500} rows={3} /></label>
    <div className="memory-actions"><button type="submit">Save feedback</button><button type="button" onClick={() => onSave(null, "")}>Clear feedback</button></div></fieldset>
    <button type="button" disabled={busy} onClick={onReload}>{conflict ? "Discard feedback draft and reload" : "Cancel feedback changes"}</button></form>;
}
export default function DiscoveryPanel({ session, onUnauthorized }: { session: Session; onUnauthorized: () => void }) {
  const scopes = session.user.scopes.filter((s): s is ProposalInput["scope"] => s === "member_a_private" || s === "member_b_private");
  const [page, setPage] = useState<Proposals | null>(null); const [selected, setSelected] = useState<Proposal | null>(null);
  const [creating, setCreating] = useState<"idea" | "proposal" | null>(null); const [editingDetails, setEditingDetails] = useState(false); const [draft, setDraft] = useState(false); const [conflict, setConflict] = useState(false);
  const [dismissed, setDismissed] = useState(false); const [cursor, setCursor] = useState<Cursor | null>(null);
  const [previous, setPrevious] = useState<(Cursor | null)[]>([]); const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const [filters, setFilters] = useState<InboxFilters>(emptyInboxFilters), [filterDraft, setFilterDraft] = useState<InboxFilters>(emptyInboxFilters);
  const [digest, setDigest] = useState<DigestReview | null>(null), [digestEpoch, setDigestEpoch] = useState(0), [digestDeadline, setDigestDeadline] = useState<number | null>(null);
  const digestController = useRef<AbortController | null>(null), copyUrls = useRef(new Set<string>());
  const requests = useRef(new Set<AbortController>());
  useEffect(() => () => { requests.current.forEach(c => c.abort()); requests.current.clear(); copyUrls.current.forEach(url => URL.revokeObjectURL(url)); copyUrls.current.clear(); }, []);
  function clearDigest(close = true) {
    const controller = digestController.current;
    if (controller) { controller.abort(); requests.current.delete(controller); digestController.current = null; setBusy(false); }
    setDigest(null); setDigestDeadline(null); if (close) setDigestEpoch(value => value + 1);
  }
  useEffect(() => {
    if (digestDeadline === null) return;
    const timer = window.setTimeout(() => { clearDigest(); copyUrls.current.forEach(url => URL.revokeObjectURL(url)); copyUrls.current.clear(); setMessage("The digest review expired. Prepare a fresh selection."); }, Math.max(0, digestDeadline - performance.now()));
    return () => window.clearTimeout(timer);
  }, [digestDeadline]);
  function reset() { clearDigest(); setSelected(null); setCreating(null); setEditingDetails(false); setDraft(false); setConflict(false); setError(""); setMessage(""); }
  function failure(err: unknown) {
    if (err instanceof MemoryError && err.status === 409) { setConflict(true); setError(editingDetails ? "This record changed. Your details draft is kept; discard it and reload before saving." : "This proposal changed. Your feedback draft is kept; discard it and reload before saving."); return; }
    if (!(err instanceof MemoryError) || [401, 403, 404, 410].includes(err.status)) {
      requests.current.forEach(c => c.abort()); requests.current.clear(); reset(); setPage(null); setBusy(false); setLoading(false);
      if (err instanceof MemoryError && err.status === 401) onUnauthorized();
    }
    setError(err instanceof MemoryError && err.status === 422 ? "Check the proposal, evidence date and fields. Invalid saved proposals can be inspected or forgotten in Memory." : "Discovery is unavailable. Refresh or try again.");
  }
  useEffect(() => {
    const controller = new AbortController(); requests.current.add(controller); setLoading(true); setPage(null);
    clearDigest();
    searchProposals(filters, dismissed, cursor, session.csrfToken, controller.signal).then(value => { if (!controller.signal.aborted) setPage(value); }).catch(err => { if (!controller.signal.aborted) failure(err); }).finally(() => { requests.current.delete(controller); if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [dismissed, cursor, reload, filters]);
  async function action(work: (signal: AbortSignal) => Promise<Proposal>, success: (value: Proposal) => void) {
    if (busy) return; const controller = new AbortController(); requests.current.add(controller); setBusy(true); setError(""); setMessage("");
    try { const value = await work(controller.signal); if (!controller.signal.aborted) success(value); }
    catch (err) { if (!controller.signal.aborted) failure(err); }
    finally { requests.current.delete(controller); if (!controller.signal.aborted) setBusy(false); }
  }
  function saved(value: Proposal) { setSelected(value); setCreating(null); setEditingDetails(false); setDraft(false); setConflict(false); setCursor(null); setPrevious([]); setReload(v => v + 1); setMessage("Saved locally. Interest does not authorize any action."); }
  function reloadSelected() { if (!selected) return; const id = selected.id; reset(); void action(signal => readProposal(id, signal), setSelected); }
  async function digestJob(request: DigestRequest, title?: string) {
    if (busy || digestController.current) return;
    const controller = new AbortController(), started = performance.now(); digestController.current = controller; requests.current.add(controller); setBusy(true); setError(""); setMessage("");
    try {
      const value = await prepareDigest(request, session, controller.signal);
      if (controller.signal.aborted) return;
      const deadline = started + Date.parse(value.valid_until) - Date.parse(value.checked_at);
      if (deadline <= performance.now()) throw new DigestError("The digest response expired. Prepare a fresh review.");
      if (title === undefined) { setDigest(value); setDigestDeadline(old => old === null ? deadline : Math.min(old, deadline)); }
      else {
        const copy = digestMarkdown(value, title), url = URL.createObjectURL(new Blob([copy.text], { type: "text/markdown;charset=utf-8" })); copyUrls.current.add(url);
        const anchor = document.createElement("a"); anchor.href = url; anchor.download = copy.filename; document.body.append(anchor);
        try { anchor.click(); } finally { anchor.remove(); window.setTimeout(() => { URL.revokeObjectURL(url); copyUrls.current.delete(url); }, 1000); }
        clearDigest(); setMessage("A Discovery digest download was requested. Manage this separate copy and its expiry yourself.");
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        clearDigest();
        if (err instanceof MemoryError && [401, 403, 404, 410].includes(err.status)) failure(err);
        else setError(err instanceof MemoryError && err.status === 409 ? "The digest review or selected records changed. Prepare a fresh selection." : err instanceof MemoryError && err.status === 413 ? "The digest is too large. Select fewer records." : err instanceof DigestError ? err.message : "The digest could not be prepared. Refresh current records.");
      }
    } finally { requests.current.delete(controller); if (digestController.current === controller) digestController.current = null; if (!controller.signal.aborted) setBusy(false); }
  }
  function downloadDigest(title: string) {
    if (!digest) return;
    void digestJob({ ...digest.request, purpose: "download", review_id: digest.review_id, reviewed_hash: digest.reviewed_hash, acknowledge_copy_limits: true }, title);
  }
  function applyFilters(value: InboxFilters) { reset(); setFilters({ ...value, q: value.q.trim(), topic: value.topic.trim() }); setCursor(null); setPrevious([]); }
  const blocked = busy || !!creating || editingDetails || draft;
  return <section aria-label="Discovery" className="memory-panel"><div className="section-heading"><div><p className="eyebrow">Discovery &amp; Innovation</p><h2>Research proposals</h2><p>Record explicit interests. Research, experiments and adoption require their own review.</p></div><div className="memory-actions"><button disabled={blocked || !scopes.length} onClick={() => { reset(); setCreating("idea"); }}>Add idea</button><button disabled={blocked || !scopes.length} onClick={() => { reset(); setCreating("proposal"); }}>Add proposal</button></div></div>
    <p className="hint">Manual evidence · no source verification or collection · no model calls · no automatic actions</p>
    <div className="memory-actions"><label className="check"><input type="checkbox" aria-label="Include dismissed proposals" checked={dismissed} disabled={blocked} onChange={e => { reset(); setDismissed(e.target.checked); setCursor(null); setPrevious([]); }} />Include dismissed proposals</label><button disabled={blocked || loading} onClick={() => { reset(); setReload(v => v + 1); }}>Refresh proposals</button></div>
    <form aria-label="Discovery inbox filters" className="discovery-inbox-filters" onSubmit={e => { e.preventDefault(); applyFilters(filterDraft); }}><fieldset disabled={blocked}>
      <label>Search saved ideas and proposals<input aria-label="Search Discovery inbox" type="search" maxLength={120} value={filterDraft.q} onChange={e => { clearDigest(); setFilterDraft(v => ({ ...v, q: e.target.value })); }} /></label>
      <label>Exact topic<input aria-label="Discovery topic filter" maxLength={64} pattern="[a-z0-9][a-z0-9\-]*" placeholder="All topics" value={filterDraft.topic} onChange={e => { clearDigest(); setFilterDraft(v => ({ ...v, topic: e.target.value })); }} /></label>
      <label>Evidence stage<select aria-label="Discovery stage filter" value={filterDraft.stage} onChange={e => { clearDigest(); setFilterDraft(v => ({ ...v, stage: e.target.value as InboxFilters["stage"] })); }}><option value="all">Ideas and proposals</option><option value="idea">Ideas without evidence</option><option value="proposal">Manually reported proposals</option></select></label>
      <label>Current interest<select aria-label="Discovery interest filter" value={filterDraft.interest} onChange={e => { clearDigest(); setFilterDraft(v => ({ ...v, interest: e.target.value as InboxFilters["interest"] })); }}><option value="all">All current interests</option><option value="unanswered">No current interest recorded</option>{Object.entries(choices).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <div className="memory-actions"><button type="submit">Apply inbox filters</button><button type="button" onClick={() => { const empty = emptyInboxFilters(); setFilterDraft(empty); applyFilters(empty); }}>Reset inbox filters</button></div>
    </fieldset><p className="hint">Filters apply to your currently authorized private records on the server; pages are live. Dismissed interests require the explicit option above. Search text stays out of URLs.</p></form>
    <DiscoveryDigestPanel key={`digest-${digestEpoch}`} rows={page?.items ?? []} blocked={blocked || loading} busy={busy && digestController.current !== null} preview={digest} onPrepare={request => { setDigest(null); void digestJob(request); }} onDownload={downloadDigest} onInvalidate={() => { clearDigest(false); setSelected(null); setConflict(false); }} onClose={() => clearDigest()} />
    <p className="hint">Order: very interested (100), later (10), unanswered (0), covered (−10), not relevant (−20). Live pages, up to 25 proposals; feedback restarts paging.</p>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status">{message}</p>}{busy && <p role="status">Working…</p>}
    <div className="memory-layout"><div>{loading ? <p role="status">Loading proposals…</p> : page?.items.length === 0 ? <p>No proposals match this view.</p> : <ul className="memory-list">{page?.items.map(entry => <li key={entry.id}><button disabled={blocked} aria-pressed={selected?.id === entry.id} onClick={() => { reset(); void action(signal => readProposal(entry.id, signal), setSelected); }}><strong>{entry.title}</strong><span>{isIdea(entry) ? "Idea - no evidence" : entry.content.topic} · Interest score {entry.priority}</span></button></li>)}</ul>}
      <nav aria-label="Proposal pages" className="memory-actions"><button disabled={blocked || loading || !previous.length} onClick={() => { reset(); const old = [...previous]; setCursor(old.pop() ?? null); setPrevious(old); }}>Previous proposals</button><button disabled={blocked || loading || !page?.next_cursor} onClick={() => { reset(); setPrevious([...previous, cursor]); setCursor(page!.next_cursor); }}>Next proposals</button></nav></div><div>
      {creating === "idea" ? <IdeaCapture scopes={scopes} busy={busy} onSave={body => { void action(signal => createIdea(body, session.csrfToken, signal), saved); }} onCancel={reset} /> : creating === "proposal" ? <ProposalCapture scopes={scopes} busy={busy} onSave={body => { void action(signal => createProposal(body, session.csrfToken, signal), saved); }} onCancel={reset} /> : selected && <article aria-label="Discovery proposal" className="memory-detail"><h3>{selected.title}</h3><p>{memoryScopes[selected.scope]} · Revision {selected.revision} · Interest score {selected.priority}</p><p className="memory-text">{selected.content.summary}</p><p className="capture-stage">{isIdea(selected) ? "Idea - no evidence supplied. Topic and assessments may be unclassified or unknown." : "Manually reported proposal - sources have not been independently verified."}</p>
        {!editingDetails && <button disabled={busy || draft} onClick={() => setEditingDetails(true)}>{isIdea(selected) ? "Add evidence and enrich idea" : "Edit proposal details"}</button>}
        {editingDetails ? <ProposalCapture key={`${selected.id}-${selected.revision}-details`} scopes={scopes} entry={selected} busy={busy} conflict={conflict} onSave={body => { const { scope: _scope, ...details } = body; void action(signal => saveProposalDetails(selected, details, session.csrfToken, signal), saved); }} onCancel={reloadSelected} /> : <>
        <h4>Manually reported evidence</h4>{!selected.content.evidence.length && <p>No evidence supplied. Add an explicit source and observed date when available; no date is invented.</p>}<ul>{selected.content.evidence.map((e, i) => <li key={i}><strong>{e.title}</strong><p className="memory-text">{e.url}</p><p>Observed: {new Date(e.observed_at).toLocaleString()}</p></li>)}</ul>
        <dl>{([['benefit', 'Expected benefit'], ['privacy', 'Privacy'], ['maturity_license', 'Maturity / license'], ['hardware_cost', 'Hardware / cost'], ['alternatives_dependencies', 'Alternatives / dependencies'], ['experiment', 'Proposed experiment']] as const).map(([field, label]) => <div key={field}><dt>{label}</dt><dd className="memory-text">{selected.content[field]}</dd></div>)}</dl>
        <p>Feedback applies to this proposal only. It does not permit installations, file access, experiments or deployment.</p>
        <FeedbackForm key={`${selected.id}-${selected.revision}`} entry={selected} busy={busy} conflict={conflict} onChange={() => setDraft(true)} onSave={(choice, note) => { void action(signal => saveFeedback(selected, choice, note, session.csrfToken, signal), saved); }} onReload={reloadSelected} />
        </>}
        <p className="hint">Use the Memory tab for this entry’s history, JSON export, metadata corrections and forgetting. Clearing feedback retains history; forgetting removes live content and saved revisions.</p>
      </article>}
    </div></div></section>;
}
