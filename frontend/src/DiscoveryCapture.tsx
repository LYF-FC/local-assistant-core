import { useState } from "react";
import type { FormEvent } from "react";
import { memoryScopes } from "./memory-api";
import type { IdeaInput, Proposal, ProposalInput } from "./discovery-api";
import { suggestedTitle } from "./capture";

const assessments = [['benefit', 'Expected benefit'], ['privacy', 'Privacy assessment'], ['maturity_license', 'Maturity and license'], ['hardware_cost', 'Hardware and cost'], ['alternatives_dependencies', 'Alternatives and dependencies'], ['experiment', 'Proposed experiment']] as const;
function localDate(value: string) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19); }
export function IdeaCapture({ scopes, busy, onSave, onCancel }: { scopes: IdeaInput["scope"][]; busy: boolean; onSave: (body: IdeaInput) => void; onCancel: () => void }) {
  const [summary, setSummary] = useState(""), [title, setTitle] = useState<string | null>(null);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const data = new FormData(event.currentTarget);
    onSave({ scope: String(data.get("scope")) as IdeaInput["scope"], title: (title ?? suggestedTitle(summary)).trim(), summary: summary.trim(), ...(data.get("topic") ? { topic: String(data.get("topic")).trim() } : {}) });
  }
  return <form aria-label="New Discovery idea" className="memory-editor" onSubmit={submit}><h3>Save an idea first</h3><p>No evidence yet · Tentative · Assessments not assessed. Add sources later; nothing is researched or approved automatically.</p><fieldset disabled={busy}>
    <label>What is the idea?<textarea aria-label="Idea summary" value={summary} onChange={e => setSummary(e.target.value)} maxLength={1000} rows={4} required /></label>
    <label>Title<input aria-label="Idea title" value={title ?? suggestedTitle(summary)} onChange={e => setTitle(e.target.value)} maxLength={160} required /></label><p className="hint">The title starts from your first nonblank line. You can edit it before saving.</p>
    <label>Private access<select aria-label="Idea private access" name="scope">{scopes.map(scope => <option key={scope} value={scope}>{memoryScopes[scope]}</option>)}</select></label>
    <details className="capture-details"><summary>Optional topic</summary><label>Topic<input aria-label="Idea topic" name="topic" maxLength={64} pattern="[a-z0-9][a-z0-9\-]*" placeholder="unclassified" /></label></details>
    <button type="submit">Save idea</button></fieldset><button type="button" disabled={busy} onClick={onCancel}>Cancel idea</button></form>;
}
export function ProposalCapture({ scopes, entry, busy, conflict = false, onSave, onCancel }: { scopes: ProposalInput["scope"][]; entry?: Proposal; busy: boolean; conflict?: boolean; onSave: (body: ProposalInput) => void; onCancel: () => void }) {
  const [evidence, setEvidence] = useState(() => (entry?.content.evidence.length ? entry.content.evidence : [{ title: "", url: "", observed_at: "" }]).map((e, index) => ({ key: index, title: e.title, url: e.url, observed: e.observed_at ? localDate(e.observed_at) : "", originalObserved: e.observed_at || null })));
  const [serial, setSerial] = useState(evidence.length), [error, setError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || conflict) return;
    const data = new FormData(event.currentTarget), text = (key: string) => String(data.get(key) ?? "").trim();
    try {
      const body: ProposalInput = { scope: entry?.scope as ProposalInput["scope"] ?? text("scope") as ProposalInput["scope"], title: text("title"), topic: text("topic"), summary: text("summary"), evidence: evidence.map(e => ({ title: e.title.trim(), url: e.url.trim(), observed_at: e.originalObserved ?? new Date(e.observed).toISOString() })) };
      for (const [field] of assessments) if (text(field)) body[field] = text(field);
      setError(""); onSave(body);
    } catch { setError("Enter a title, public HTTPS reference and explicit observed date for each evidence row."); }
  }
  function update(key: number, field: "title" | "url" | "observed", value: string) { setEvidence(rows => rows.map(e => e.key === key ? { ...e, [field]: value, ...(field === "observed" ? { originalObserved: null } : {}) } : e)); }
  return <form aria-label={entry ? "Edit Discovery details" : "New Discovery proposal"} className="memory-editor" onSubmit={submit}><h3>{entry ? "Review and enrich this idea or proposal" : "Add a manual proposal"}</h3><p>Sources are manually reported, not fetched or verified. Blank assessments remain Not assessed; an experiment remains Not proposed.</p><fieldset disabled={busy || conflict}>
    <label>Title<input aria-label="Proposal title" name="title" required maxLength={160} defaultValue={entry?.title ?? ""} /></label>
    <label>Topic<input aria-label="Proposal topic" name="topic" required maxLength={64} pattern="[a-z0-9][a-z0-9\-]*" placeholder="local-photo-tagging" defaultValue={entry?.content.topic ?? ""} /></label>
    <label>Summary<textarea aria-label="Proposal summary" name="summary" required maxLength={1000} rows={3} defaultValue={entry?.content.summary ?? ""} /></label>
    {entry ? <p>Private access: {memoryScopes[entry.scope]} · Revision {entry.revision}. Ownership and access stay unchanged.</p> : <label>Private access<select aria-label="Proposal private access" name="scope">{scopes.map(scope => <option key={scope} value={scope}>{memoryScopes[scope]}</option>)}</select></label>}
    <section aria-label="Manually reported evidence"><h4>Evidence · 1–5 explicit references</h4>{evidence.map((e, index) => <fieldset className="capture-evidence" key={e.key}><legend>Evidence {index + 1}</legend>
      <label>Evidence title<input aria-label={index === 0 ? "Evidence title" : `Evidence ${index+1} title`} required maxLength={160} value={e.title} onChange={event => update(e.key, "title", event.target.value)} /></label>
      <label>Evidence URL<input aria-label={index === 0 ? "Evidence URL" : `Evidence ${index+1} URL`} type="url" required maxLength={512} placeholder="https://…" value={e.url} onChange={event => update(e.key, "url", event.target.value)} /></label>
      <label>Evidence observed at (your local time)<input aria-label={index === 0 ? "Evidence observed at" : `Evidence ${index+1} observed at`} type="datetime-local" step="1" required value={e.observed} onChange={event => update(e.key, "observed", event.target.value)} /></label>
      {evidence.length > 1 && <button type="button" onClick={() => setEvidence(rows => rows.filter(row => row.key !== e.key))}>Remove evidence {index+1}</button>}
    </fieldset>)}<button type="button" disabled={evidence.length >= 5} onClick={() => { setEvidence(rows => [...rows, { key: serial, title: "", url: "", observed: "", originalObserved: null }]); setSerial(n => n + 1); }}>Add evidence row</button></section>
    <details className="capture-details"><summary>Optional assessments and experiment</summary>{assessments.map(([name, label]) => <label key={name}>{label}<textarea aria-label={label} name={name} maxLength={name === "experiment" ? 1000 : 512} rows={2} defaultValue={entry?.content[name] ?? ""} /></label>)}</details>
    <button type="submit">{entry ? "Save reviewed details" : "Save proposal"}</button></fieldset>
    {error && <p role="alert" className="error">{error}</p>}{conflict && <p>This record changed. Your details draft is kept; discard it and reload before saving.</p>}
    <button type="button" disabled={busy} onClick={onCancel}>{conflict ? "Discard details draft and reload" : entry ? "Cancel details changes" : "Cancel proposal"}</button></form>;
}
