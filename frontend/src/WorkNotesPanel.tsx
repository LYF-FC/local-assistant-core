import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Session } from "./api";
import WorkDebriefPanel from "./WorkDebriefPanel";
import WorkExportPanel from "./WorkExportPanel";
import WorkReviewPanel from "./WorkReviewPanel";
import { reviewMarkdown } from "./work-review-markdown";
import type { ReviewOptions } from "./work-review";
import WorkMeetingPanel from "./WorkMeetingPanel";
import { meetingMarkdown } from "./work-meeting-markdown";
import { MeetingError } from "./work-meeting";
import type { MeetingOptions } from "./work-meeting";
import { proposalOutcome } from "./work-debrief";
import type { DebriefProposal, ProposalRequest, ProposalState } from "./work-debrief";
import { catalogue, inspect, NotesError, prepareExport, recovered, submit } from "./work-notes-api";
import type { Ack, Action, Catalogue, Choice, Draft, ExportRequest, Frame, Inspection, NoteRow, NotesExport, Pages, Policy, RequestRow, Section } from "./work-notes-api";

type Binding = Pick<Action, "operation" | "request_id" | "target_record_id" | "expected_revision">;
const names = { capture_draft: "Save draft", correct_note: "Correct note", forget_note: "Forget note", confirm_note: "Confirm version" };
const dateLabel = (v: string) => new Date(v).toLocaleString();
const noteLabel = (n: NoteRow) => n.label ?? `${n.state === "forgotten" ? "Forgotten" : "Unavailable"} note · ${n.id.slice(-8)}`;
const duration = (n: number) => n >= 86400 ? `${Math.round(n / 86400)} day${n === 86400 ? "" : "s"}` : n >= 3600 ? `${Math.round(n / 3600)} hour${n === 3600 ? "" : "s"}` : `${n} seconds`;
function localDate(v: string | null) { if (!v) return ""; const d = new Date(v); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); }
function merge<T extends { id: string }>(items: T[], selected: T[]) { return [...items, ...selected.filter(s => !items.some(i => i.id === s.id))]; }

function Editor({ detail, initial, pages, busy, serverNow, onSave, onCancel, onMore }: { detail: Inspection | null; initial: DebriefProposal | null; pages: Pages; busy: boolean; serverNow: () => number; onSave: (draft: Draft, policy: string) => void; onCancel: () => void; onMore: (section: Section) => void }) {
  const [text, setText] = useState(detail?.item.marker.slice(10) ?? initial?.text ?? "");
  const [kind, setKind] = useState(detail?.item.kind ?? initial?.kind ?? "observation");
  const [sources, setSources] = useState<Choice[]>(detail?.references.sources ?? []);
  const [policy, setPolicy] = useState<Policy | null>(detail?.references.policy ?? null);
  const [owner, setOwner] = useState<Choice | null>(detail?.references.owner?.available ? { id: detail.references.owner.id, label: detail.references.owner.label! } : null);
  const [ownerValue, setOwnerValue] = useState(detail?.item.owner_id ? (detail.references.owner?.available ? detail.item.owner_id : "") : "unknown");
  const [keep, setKeep] = useState(detail ? "current" : "");
  const [due, setDue] = useState(localDate(detail?.item.due_at ?? null));
  const [error, setError] = useState("");
  const availableSources = merge(pages.sources?.items ?? [], sources);
  const policies = merge(pages.policies?.items ?? [], policy ? [policy] : []);
  const owners = merge(pages.parties?.items ?? [], owner ? [owner] : []);
  const max = policy ? Math.min(policy.max_age_seconds, detail ? Math.max(0, (Date.parse(detail.item.retain_until) - serverNow()) / 1000) : policy.max_age_seconds) : 0;
  const periods = [...new Set([3600, 86400, 604800, ...(policy ? [policy.max_age_seconds] : [])])].filter(v => v <= max).sort((a, b) => a - b);
  function send(e: FormEvent) {
    e.preventDefault();
    if (busy || !policy || !sources.length || !ownerValue || !keep || !text.trim()) { setError("Choose sources, a retention policy and an expiry. Owner may stay Unknown."); return; }
    const marker = `synthetic:${text.trim()}`;
    if (!/^synthetic:[a-zA-Z0-9 _.-]+$/.test(marker) || marker.length > 256) { setError("Use sample text with letters, numbers, spaces, dots, underscores or hyphens."); return; }
    onSave({ kind, marker, source_ids: sources.map(s => s.id), owner_id: ownerValue === "unknown" ? null : ownerValue, due_at: due ? new Date(due).toISOString() : null, retain_until: keep === "current" && detail ? detail.item.retain_until : new Date(serverNow() + Number(keep) * 1000).toISOString() }, policy.id);
  }
  return <form aria-label={detail ? "Correct sample note" : "New sample note"} className="memory-editor" onSubmit={send}>
    <h3>{detail ? "Correct this note" : "Capture a sample note"}</h3>
    {initial && <div className="work-debrief-origin"><p>Reviewing debrief line {initial.line}. Original wording:</p><blockquote><p className="work-debrief-quote">{initial.quote}</p></blockquote></div>}
    <fieldset disabled={busy}>
      <label>Sample note<textarea autoFocus={!!initial} aria-label="Sample note" required maxLength={246} rows={3} value={text} onChange={e => setText(e.target.value)} /></label>
      <label>Note type<select aria-label="Note type" disabled={!!detail} value={kind} onChange={e => setKind(e.target.value as Draft["kind"])}><option value="observation">Observation</option><option value="question">Question</option><option value="decision">Decision</option><option value="action">Action</option></select></label>
      <fieldset className="work-source-choices"><legend>Sources · choose 1–10</legend>{availableSources.map(s => <label className="work-check" key={s.id}><input type="checkbox" checked={sources.some(v => v.id === s.id)} disabled={sources.length >= 10 && !sources.some(v => v.id === s.id)} onChange={e => setSources(e.target.checked ? [...sources, s] : sources.filter(v => v.id !== s.id))} />{s.label}</label>)}{!availableSources.length && <p>No active sample sources are available.</p>}
        {pages.sources?.next_cursor && <button type="button" onClick={() => onMore("sources")}>More sources</button>}</fieldset>
      <label>Retention policy<select aria-label="Retention policy" required disabled={!!detail} value={policy?.id ?? ""} onChange={e => { setPolicy(policies.find(p => p.id === e.target.value) ?? null); setKeep(""); }}><option value="">Choose a policy</option>{policies.map(p => <option value={p.id} key={p.id}>Up to {duration(p.max_age_seconds)}</option>)}</select></label>
      {!detail && pages.policies?.next_cursor && <button type="button" onClick={() => onMore("policies")}>More policies</button>}
      <label>Keep until<select aria-label="Keep until" required value={keep} onChange={e => setKeep(e.target.value)}><option value="">Choose retention</option>{detail && <option value="current">Current expiry · {dateLabel(detail.item.retain_until)}</option>}{periods.map(p => <option value={String(p)} key={p}>{duration(p)} from now</option>)}</select></label>
      <label>Owner · optional<select aria-label="Owner" required value={ownerValue} onChange={e => { setOwnerValue(e.target.value); setOwner(owners.find(p => p.id === e.target.value) ?? null); }}><option value="">Choose a current owner or Unknown</option><option value="unknown">Unknown</option>{owners.map(p => <option value={p.id} key={p.id}>{p.label}</option>)}</select></label>
      {detail?.references.owner && !detail.references.owner.available && <p>The previous owner is unavailable. Choose a current owner or Unknown explicitly.</p>}
      {pages.parties?.next_cursor && <button type="button" onClick={() => onMore("parties")}>More owners</button>}
      <label>Due date · optional<input aria-label="Due date" type="datetime-local" value={due} onChange={e => setDue(e.target.value)} /></label>
      <button type="submit">{detail ? "Request correction" : "Request save"}</button>
    </fieldset>
    {error && <p role="alert">{error}</p>}<button type="button" disabled={busy} onClick={onCancel}>Cancel editing</button>
  </form>;
}

function ForgetDialog({ note, busy, onConfirm, onCancel }: { note: NoteRow; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current!; d.showModal(); return () => d.close(); }, []);
  return <dialog ref={ref} aria-labelledby="work-forget-title" onCancel={e => { e.preventDefault(); if (!busy) onCancel(); }}><h3 id="work-forget-title">Forget this sample note?</h3><p>{noteLabel(note)} · version {note.revision}</p><p>Once applied, this removes the live note, its saved revisions and pending corrections. Older backups and independent copies may remain.</p><p>This sends a request; forgetting is not immediate.</p><div className="memory-actions"><button disabled={busy} onClick={onCancel}>Keep note</button><button className="danger" disabled={busy} onClick={onConfirm}>Request forgetting</button></div></dialog>;
}

export default function WorkNotesPanel({ workspace, session, onUnauthorized }: { workspace: string; session: Session; onUnauthorized: () => void }) {
  const [catalog, setCatalog] = useState<Catalogue | null>(null);
  const [detail, setDetail] = useState<Inspection | null>(null);
  const [editing, setEditing] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [exportPreview, setExportPreview] = useState<NotesExport | null>(null);
  const [exportEpoch, setExportEpoch] = useState(0);
  const [meetingPreview, setMeetingPreview] = useState<NotesExport | null>(null);
  const [meetingEpoch, setMeetingEpoch] = useState(0);
  const [reviewPreview, setReviewPreview] = useState<NotesExport | null>(null);
  const [reviewEpoch, setReviewEpoch] = useState(0);
  const exportController = useRef<AbortController | null>(null);
  const exportUrls = useRef(new Set<string>());
  const [seed, setSeed] = useState<DebriefProposal | null>(null);
  const [debriefEpoch, setDebriefEpoch] = useState(0);
  const [proposalStates, setProposalStates] = useState<Record<number, ProposalState>>({});
  const proposalRequest = useRef<ProposalRequest | null>(null);
  const [forget, setForget] = useState<NoteRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [binding, setBinding] = useState<Binding | null>(null);
  const [ack, setAck] = useState<(Ack & { operation: Action["operation"] }) | null>(null);
  const [deadline, setDeadline] = useState<number | null>(null);
  const active = useRef(new Set<AbortController>());
  const action = useRef<Action | null>(null);
  const clock = useRef({ server: 0, mono: 0 });
  const saving = useRef(false);
  const writeController = useRef<AbortController | null>(null);
  useEffect(() => () => { active.current.forEach(c => c.abort()); active.current.clear(); action.current = null; exportUrls.current.forEach(url => URL.revokeObjectURL(url)); exportUrls.current.clear(); }, []);
  function serverNow() { return clock.current.server + Math.max(0, performance.now() - clock.current.mono); }
  function abortDerived() {
    const controller = exportController.current;
    if (controller) { controller.abort(); active.current.delete(controller); exportController.current = null; setBusy(false); }
  }
  function resetExport() {
    abortDerived();
    setExportPreview(null); setExportEpoch(value => value + 1);
    setMeetingPreview(null); setMeetingEpoch(value => value + 1);
    setReviewPreview(null); setReviewEpoch(value => value + 1);
  }
  function clearPrivate() { resetExport(); exportUrls.current.forEach(url => URL.revokeObjectURL(url)); exportUrls.current.clear(); setSeed(null); setProposalStates({}); proposalRequest.current = null; active.current.forEach(c => c.abort()); active.current.clear(); setCatalog(null); setDetail(null); setEditing(false); setCorrecting(false); setForget(null); action.current = null; setDeadline(null); setBusy(false); saving.current = false; writeController.current = null; }
  useEffect(() => {
    if (deadline === null) return;
    const timer = window.setTimeout(() => { clearPrivate(); setMessage("The preview expired. Reload current notes and options. Request references can still be reconciled."); }, Math.max(0, deadline - performance.now()));
    return () => window.clearTimeout(timer);
  }, [deadline]);
  function adopt(value: Frame, started: number) {
    const limit = started + Date.parse(value.valid_until) - Date.parse(value.checked_at);
    if (limit <= performance.now()) throw new Error("Expired response");
    setDeadline(previous => previous === null ? limit : Math.min(previous, limit));
    clock.current = { server: Date.parse(value.checked_at), mono: performance.now() };
  }
  function denied(err: unknown) {
    clearPrivate(); setAck(null); setMessage(""); setError(err instanceof NotesError || err instanceof MeetingError ? err.message : "The response could not be verified. Reload current access.");
    if (err instanceof NotesError && err.status === 401) onUnauthorized();
  }
  async function read<T>(job: (signal: AbortSignal) => Promise<T>, done: (value: T, started: number) => void, exporting = false) {
    active.current.forEach(previous => previous.abort()); active.current.clear(); exportController.current = null;
    const c = new AbortController(), started = performance.now(); active.current.add(c); if (exporting) exportController.current = c; setBusy(true); setError("");
    try { const value = await job(c.signal); if (!c.signal.aborted) done(value, started); }
    catch (err) { if (!c.signal.aborted) denied(err); }
    finally { active.current.delete(c); if (exportController.current === c) exportController.current = null; if (!c.signal.aborted) setBusy(false); }
  }
  function load() {
    clearPrivate(); setMessage("");
    void read(signal => catalogue(workspace, session, signal), (value, started) => { adopt(value, started); setCatalog(value); });
  }
  function more(section: Section) {
    resetExport();
    const after = catalog?.pages[section]?.next_cursor; if (!after) return;
    void read(signal => catalogue(workspace, session, signal, section, after), (value, started) => { adopt(value, started); setCatalog(old => old ? { ...old, features: value.features, pages: { ...old.pages, ...value.pages } } : value); });
  }
  function open(record: string) {
    resetExport(); setSeed(null); setDetail(null); setEditing(false); setCorrecting(false); setMessage("");
    void read(signal => inspect(workspace, record, session, signal), (value, started) => { adopt(value, started); setDetail(value); });
  }
  function discardDebrief() {
    if (saving.current) return;
    if (proposalRequest.current) action.current = null;
    proposalRequest.current = null; setSeed(null); setProposalStates({}); setDebriefEpoch(value => value + 1); setEditing(false); setCorrecting(false);
  }
  function chooseProposal(proposal: DebriefProposal) {
    if (saving.current || busy || binding || (catalog?.pages.requests?.pending_count ?? 0) > 0) return;
    setDetail(null); setCorrecting(false); setSeed(proposal); setEditing(true);
  }
  function markProposal(nonce: string, state: ProposalState) {
    const outcome = proposalOutcome(proposalRequest.current, nonce, state);
    if (outcome) setProposalStates(previous => ({ ...previous, [outcome.line]: outcome.state }));
  }
  function accepted(value: Ack, op: Action["operation"], nonce: string) {
    if (op === "capture_draft") markProposal(nonce, value.state);
    setSeed(null);
    setAck({ ...value, operation: op }); setDetail(null); setEditing(false); setCorrecting(false); setForget(null);
    if (value.state !== "pending") { action.current = null; setBinding(null); }
    setMessage(value.state === "pending" ? "Request recorded and awaiting separate local processing. It has not been applied. Refresh its status after processing." : value.state === "applied" ? "The request was applied. Its result below is historical; open the note to inspect its current version." : "The request was not applied. Reload the current note before making another request.");
  }
  async function send(next: Action) {
    if (saving.current) return;
    resetExport(); saving.current = true; action.current = next; setBinding({ operation: next.operation, request_id: next.request_id, target_record_id: next.target_record_id, expected_revision: next.expected_revision }); setAck(null); setError(""); setBusy(true);
    const c = new AbortController(); writeController.current = c; active.current.add(c);
    try { const value = await submit(workspace, next, session, c.signal); if (!c.signal.aborted) accepted(value, next.operation, next.request_id); }
    catch (err) {
      if (c.signal.aborted) return;
      if (err instanceof NotesError && [401, 403, 404, 503].includes(err.status)) denied(err);
      else { markProposal(next.request_id, "uncertain"); setSeed(null); setDetail(null); setEditing(false); setCorrecting(false); setForget(null); setError("The request response is uncertain. Recover its status or retry the same request before making another change."); }
    } finally { active.current.delete(c); if (writeController.current === c) { saving.current = false; writeController.current = null; } if (!c.signal.aborted) setBusy(false); }
  }
  function recover(reference: Binding) {
    void read(signal => catalogue(workspace, session, signal, "requests", null, reference), (value, started) => {
      adopt(value, started); setCatalog(old => old ? { ...old, pages: { ...old.pages, requests: value.pages.requests } } : value);
      const found = recovered(value.pages.requests!, reference);
      if (found) { if (found.state === "pending") { setBinding(reference); if (action.current?.request_id !== reference.request_id) action.current = null; } accepted({ id: found.id, state: found.state, record_id: found.record_id, revision: found.revision, expires_at: found.expires_at }, found.operation, found.request_id); }
      else setMessage("No matching request was found in the current session. Retry only the same preserved request, or reload notes and reconcile before preparing another.");
    });
  }
  function save(draft: Draft, policy: string) {
    if (saving.current || busy || binding || (catalog?.pages.requests?.pending_count ?? 0) > 0) return;
    const request_id = crypto.randomUUID();
    proposalRequest.current = !correcting && seed ? { line: seed.line, request_id } : null;
    if (correcting && detail) void send({ operation: "correct_note", request_id, target_record_id: detail.item.id, expected_revision: detail.item.revision, body: { request_id, decision: "correct_note", expected_revision: detail.item.revision, draft } });
    else void send({ operation: "capture_draft", request_id, target_record_id: null, expected_revision: null, body: { request_id, decision: "capture_draft", policy_id: policy, draft } });
  }
  function exportNotes(request: ExportRequest) {
    if (saving.current || exportController.current || busy || binding || (catalog?.pages.requests?.pending_count ?? 0) > 0) return;
    setExportPreview(null); setMeetingPreview(null); setMeetingEpoch(value => value + 1);
    void read(signal => prepareExport(workspace, request, session, signal), (value, started) => {
      adopt(value, started); setExportPreview(value);
    }, true);
  }
  function downloadExport() {
    if (!exportPreview || saving.current || exportController.current || busy || binding) return;
    const request: ExportRequest = { selections: exportPreview.request.selections.map(s => ({ ...s })), include_drafts: exportPreview.request.include_drafts, purpose: "download", acknowledge_copy_limits: true, reviewed_hash: exportPreview.reviewed_hash };
    void read(signal => prepareExport(workspace, request, session, signal), (value, started) => {
      adopt(value, started);
      const url = URL.createObjectURL(new Blob([JSON.stringify(value.bundle)], { type: "application/json" }));
      exportUrls.current.add(url);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `butler-work-${workspace}-${value.bundle.export_id}.json`; document.body.append(anchor);
      try { anchor.click(); } finally { anchor.remove(); window.setTimeout(() => { URL.revokeObjectURL(url); exportUrls.current.delete(url); }, 1000); }
      resetExport();
      setMessage("A JSON download was requested. Manage this separate copy and its retention yourself; Butler cannot erase it later.");
    }, true);
  }
  function invalidateExport() {
    abortDerived(); setExportPreview(null);
    setMeetingPreview(null); setMeetingEpoch(value => value + 1);
    setReviewPreview(null); setReviewEpoch(value => value + 1);
  }
  function invalidateMeeting() {
    abortDerived(); setMeetingPreview(null);
    setExportPreview(null); setExportEpoch(value => value + 1);
    setReviewPreview(null); setReviewEpoch(value => value + 1);
  }
  function invalidateReview() {
    abortDerived(); setReviewPreview(null);
    setExportPreview(null); setExportEpoch(value => value + 1);
    setMeetingPreview(null); setMeetingEpoch(value => value + 1);
  }
  function prepareReview(request: ExportRequest) {
    if (saving.current || exportController.current || busy || binding || (catalog?.pages.requests?.pending_count ?? 0) > 0) return;
    setReviewPreview(null);
    void read(signal => prepareExport(workspace, request, session, signal), (value, started) => { adopt(value, started); setReviewPreview(value); }, true);
  }
  function downloadReview(options: ReviewOptions) {
    if (!reviewPreview || saving.current || exportController.current || busy || binding) return;
    const request: ExportRequest = { selections: reviewPreview.request.selections.map(selection => ({ ...selection })), include_drafts: false, purpose: "download", acknowledge_copy_limits: true, reviewed_hash: reviewPreview.reviewed_hash };
    void read(signal => prepareExport(workspace, request, session, signal), (value, started) => {
      adopt(value, started);
      const copy = reviewMarkdown(value.bundle, options);
      const url = URL.createObjectURL(new Blob([copy.text], { type: "text/markdown;charset=utf-8" }));
      exportUrls.current.add(url);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = copy.filename; document.body.append(anchor);
      try { anchor.click(); } finally { anchor.remove(); window.setTimeout(() => { URL.revokeObjectURL(url); exportUrls.current.delete(url); }, 1000); }
      resetExport(); setMessage("A work status report download was requested. Manage this separate copy and its retention yourself; Butler cannot erase it later.");
    }, true);
  }
  function prepareMeeting(request: ExportRequest) {
    if (saving.current || exportController.current || busy || binding || (catalog?.pages.requests?.pending_count ?? 0) > 0) return;
    setMeetingPreview(null); setExportPreview(null); setExportEpoch(value => value + 1);
    void read(signal => prepareExport(workspace, request, session, signal), (value, started) => {
      adopt(value, started); setMeetingPreview(value);
    }, true);
  }
  function downloadMeeting(options: MeetingOptions) {
    if (!meetingPreview || saving.current || exportController.current || busy || binding) return;
    const request: ExportRequest = { selections: meetingPreview.request.selections.map(selection => ({ ...selection })), include_drafts: false, purpose: "download", acknowledge_copy_limits: true, reviewed_hash: meetingPreview.reviewed_hash };
    void read(signal => prepareExport(workspace, request, session, signal), (value, started) => {
      adopt(value, started);
      const documentCopy = meetingMarkdown(value.bundle, options);
      const url = URL.createObjectURL(new Blob([documentCopy.text], { type: "text/markdown;charset=utf-8" }));
      exportUrls.current.add(url);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = documentCopy.filename; document.body.append(anchor);
      try { anchor.click(); } finally { anchor.remove(); window.setTimeout(() => { URL.revokeObjectURL(url); exportUrls.current.delete(url); }, 1000); }
      resetExport();
      setMessage("A meeting Markdown download was requested. Manage this separate copy and its retention yourself; Butler cannot erase it later.");
    }, true);
  }
  function confirmVersion() {
    if (!detail || busy || binding) return;
    const request_id = crypto.randomUUID();
    void send({ operation: "confirm_note", request_id, target_record_id: detail.item.id, expected_revision: detail.item.revision,
      body: { request_id, decision: "confirm_note", expected_revision: detail.item.revision },
      review: { body: { request_id: crypto.randomUUID(), decision: "approve", expected_revision: detail.item.revision, reviewed_hash: detail.payload_hash } } });
  }
  function requestForget() {
    if (!forget || saving.current || busy || binding) return;
    const request_id = crypto.randomUUID();
    discardDebrief();
    void send({ operation: "forget_note", request_id, target_record_id: forget.id, expected_revision: forget.revision, body: { request_id, decision: "forget_note", expected_revision: forget.revision } });
  }
  const pending = (catalog?.pages.requests?.pending_count ?? 0) > 0;
  const blocked = busy || !!binding || pending;
  const rows = catalog?.pages.notes?.items ?? [];
  return <section aria-label="Synthetic Work notes" className="work-notes">
    <div className="section-heading"><div><p className="eyebrow">Synthetic pilot</p><h3>Capture and review work notes</h3><p>Use sample content only. Requests need separate local processing; no model or external action runs here.</p></div><button disabled={busy} onClick={load}>{catalog ? "Reload notes and options" : "Open synthetic notes"}</button></div>
    {busy && <p role="status">Checking current work access…</p>}{error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="work-message">{message}</p>}
    {binding && <div className="work-request"><strong>{names[binding.operation]}</strong><div className="memory-actions"><button disabled={busy} onClick={() => recover(binding)}>Recover or refresh request status</button>{action.current && <button disabled={busy} onClick={() => { const original = action.current; if (original) void send(original); }}>Retry same request</button>}</div></div>}
    {ack && <section aria-label="Request outcome" className="work-request"><h4>{names[ack.operation]} · {ack.state}</h4><p>{ack.state === "pending" ? "Awaiting processing. Nothing is applied yet." : ack.state === "denied" ? "Not applied." : `Applied at version ${ack.revision}.`}</p>{ack.state === "applied" && ack.record_id && ack.operation !== "forget_note" && <button disabled={busy} onClick={() => open(ack.record_id!)}>Open resulting note</button>}<details><summary>Request reference</summary><code>{ack.id}</code><p>Request lifetime ends {dateLabel(ack.expires_at)}.</p></details></section>}
    {catalog?.pages.notes && <>
      <div className="memory-actions"><button disabled={blocked || !catalog.features.capture} onClick={() => { setSeed(null); setDetail(null); setCorrecting(false); setEditing(true); }}>New sample note</button>{pending && <p>Resolve current pending requests before submitting another change.</p>}</div>
      {catalog.features.export && <WorkExportPanel key={`export-${exportEpoch}`} rows={rows} busy={busy && exportController.current !== null} blocked={blocked} preview={exportPreview} onPrepare={exportNotes} onDownload={downloadExport} onInvalidate={invalidateExport} onClose={resetExport} />}
      {catalog.features.export && <WorkMeetingPanel key={`meeting-${meetingEpoch}`} rows={rows} busy={busy && exportController.current !== null} blocked={blocked} preview={meetingPreview} onPrepare={prepareMeeting} onDownload={downloadMeeting} onInvalidate={invalidateMeeting} onClose={resetExport} />}
      {catalog.features.export && <WorkReviewPanel key={`review-${reviewEpoch}`} rows={rows} busy={busy && exportController.current !== null} blocked={blocked} preview={reviewPreview} onPrepare={prepareReview} onDownload={downloadReview} onInvalidate={invalidateReview} onClose={resetExport} />}
      {catalog.features.capture && <WorkDebriefPanel key={`debrief-${debriefEpoch}`} disabled={blocked} busy={busy} chosenLine={seed?.line ?? null} outcomes={proposalStates} onChoose={chooseProposal} onOmit={line => { if (seed?.line === line) { setSeed(null); setEditing(false); } }} onDiscard={discardDebrief} />}
      <div className="memory-layout"><aside><h4>Notes</h4><ul className="memory-list">{rows.map(n => <li key={n.id}><button disabled={busy || !n.content_available} onClick={() => open(n.id)}><strong>{noteLabel(n)}</strong><span>{n.state} · version {n.revision}</span>{n.retain_until && <span>Expiry {dateLabel(n.retain_until)}</span>}</button>{n.state !== "forgotten" && <button className="danger" disabled={blocked || !catalog.features.changes} onClick={() => setForget(n)}>Forget {n.label ?? "unavailable note"}</button>}</li>)}</ul>{!rows.length && <p>No notes in this page.</p>}{catalog.pages.notes.next_cursor && <button disabled={busy} onClick={() => more("notes")}>Next notes</button>}</aside>
      <div>{editing ? <Editor key={correcting ? detail?.item.id : seed ? `debrief-${seed.line}` : "new"} detail={correcting ? detail : null} initial={seed} pages={catalog.pages} busy={busy} serverNow={serverNow} onSave={save} onCancel={() => { setSeed(null); setEditing(false); setCorrecting(false); }} onMore={more} /> : detail ? <section className="memory-detail" aria-label="Selected work note"><h4>{detail.item.marker.slice(10)}</h4><p>{detail.item.kind} · {detail.item.state} · version {detail.item.revision}</p><dl><dt>Sources</dt><dd>{detail.references.sources.map(s => s.label).join(", ") || "None selected"}</dd><dt>Owner</dt><dd>{detail.references.owner?.label ?? (detail.item.owner_id ? "Previous owner unavailable" : "Unknown")}</dd><dt>Due date</dt><dd>{detail.item.due_at ? dateLabel(detail.item.due_at) : "Unknown"}</dd><dt>Expiry</dt><dd>{dateLabel(detail.item.retain_until)}</dd></dl><div className="memory-actions">{detail.item.state === "draft" && <button disabled={blocked || !detail.features.review || !detail.features.confirmation || !detail.item.source_ids.length} onClick={confirmVersion}>Confirm this version</button>}<button disabled={blocked || !detail.features.changes || detail.item.revision >= 100} onClick={() => { setSeed(null); setCorrecting(true); setEditing(true); }}>Correct note</button><button className="danger" disabled={blocked || !detail.features.changes} onClick={() => setForget({ id: detail.item.id, revision: detail.item.revision, state: detail.item.state, label: detail.item.marker.slice(10), content_available: true, retain_until: detail.item.retain_until })}>Forget note</button></div><p className="hint">This is a short-lived snapshot. Every request rechecks current access and version.</p></section> : <p>Select a note to inspect it, or capture a new sample.</p>}</div></div>
    </>}
    {catalog?.pages.requests && <section aria-label="Your work requests"><h4>Your current-session requests</h4><ul className="work-requests">{catalog.pages.requests.items.map(r => <li key={r.id}><span>{names[r.operation]} · {r.state}{r.state === "pending" && !r.within_lifetime ? " · lifetime ended" : ""}</span><button disabled={busy} onClick={() => recover(r)}>Check request</button></li>)}</ul>{!catalog.pages.requests.items.length && <p>No requests in this page.</p>}{catalog.pages.requests.next_cursor && <button disabled={busy} onClick={() => more("requests")}>Next requests</button>}</section>}
    {forget && <ForgetDialog note={forget} busy={busy} onCancel={() => setForget(null)} onConfirm={requestForget} />}
  </section>;
}
