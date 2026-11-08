import { useState } from "react";
import type { FormEvent } from "react";
import { DebriefError, prepareDebrief } from "./work-debrief";
import type { DebriefProposal, ProposalState } from "./work-debrief";

const outcomeLabels = { uncertain: "Response uncertain — recover this request", pending: "Draft save awaiting processing", applied: "Draft save applied", denied: "Draft save not applied — review before requesting again" };
export default function WorkDebriefPanel({ disabled, busy, chosenLine, outcomes, onChoose, onOmit, onDiscard }: {
  disabled: boolean; busy: boolean; chosenLine: number | null; outcomes: Record<number, ProposalState>;
  onChoose: (proposal: DebriefProposal) => void; onOmit: (line: number) => void; onDiscard: () => void;
}) {
  const [started, setStarted] = useState(false);
  const [input, setInput] = useState("");
  const [proposals, setProposals] = useState<DebriefProposal[] | null>(null);
  const [error, setError] = useState("");
  function prepare(event: FormEvent) {
    event.preventDefault(); if (disabled) return;
    try { const result = prepareDebrief(input); setProposals(result); setInput(""); setError(""); }
    catch (err) { setError(err instanceof DebriefError ? err.message : "The sample debrief could not be prepared."); }
  }
  if (!started) return <button disabled={disabled} onClick={() => setStarted(true)}>New sample debrief</button>;
  return <section aria-label="Sample debrief review" className="work-debrief">
    <h4>Prepare a sample debrief</h4>
    <p>Use sample content only. Each labelled line becomes a proposal for your review. Nothing is saved or sent when preparing it.</p>
    {proposals === null ? <form aria-label="Prepare sample debrief" onSubmit={prepare}>
      <label>Sample debrief<textarea aria-label="Sample debrief" disabled={disabled} required maxLength={3000} rows={6} value={input} onChange={e => setInput(e.target.value)} aria-describedby="debrief-help" /></label>
      <p id="debrief-help" className="hint">Up to 10 lines. Start each with Observation:, Action:, Decision: or Question:. Use letters, numbers, spaces, dots, underscores or hyphens after the label.</p>
      <pre className="work-debrief-example">Action: Prepare the sample agenda{"\n"}Question: Clarify the sample dependency</pre>
      <button disabled={disabled} type="submit">Prepare proposals</button>
    </form> : <>
      <p>Compare the original line with its proposal, then review one draft at a time. Owner and due date stay Unknown unless you choose them. Names and dates in the text are not assigned automatically.</p>
      <p className="hint">Original lines are temporary review aids. Saving stores your edited note and the registered sources you choose; it does not store this debrief or its line references.</p>
      <ol className="work-debrief-proposals">{proposals.map(proposal => {
        const state = outcomes[proposal.line], locked = !!state && state !== "denied";
        return <li key={proposal.line} aria-label={`Debrief line ${proposal.line}`}>
          <h5>Line {proposal.line} · {proposal.kind}</h5><blockquote><p className="work-debrief-quote">{proposal.quote}</p></blockquote>
          <p><strong>Proposal:</strong> {proposal.text}</p>
          <p role="status">{state ? outcomeLabels[state] : chosenLine === proposal.line ? "Open for review below — not saved" : "Not requested"}</p>
          <div className="memory-actions"><button disabled={disabled || locked} onClick={() => onChoose(proposal)}>Review line {proposal.line}</button><button disabled={disabled || locked} onClick={() => { setProposals(proposals.filter(p => p.line !== proposal.line)); onOmit(proposal.line); }}>Omit line {proposal.line}</button></div>
        </li>;
      })}</ol>
      {!proposals.length && <p>No proposals remain. Discard this debrief to start another.</p>}
    </>}
    {error && <p role="alert" className="error">{error}</p>}
    <button disabled={busy} onClick={onDiscard}>Discard debrief</button>
  </section>;
}
