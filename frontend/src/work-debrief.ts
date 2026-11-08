import type { Draft } from "./work-notes-api";

export type DebriefProposal = Readonly<{ line: number; kind: Draft["kind"]; text: string; quote: string }>;
export type ProposalState = "uncertain" | "pending" | "applied" | "denied";
export type ProposalRequest = Readonly<{ line: number; request_id: string }>;
export class DebriefError extends Error {}
const kinds = { observation: "observation", action: "action", decision: "decision", question: "question" } as const;

/** Explicit annotated lines only: no inference, I/O, deduplication or implicit authority. */
export function prepareDebrief(input: string): DebriefProposal[] {
  if (!input.trim()) throw new DebriefError("Enter at least one labelled sample line.");
  if (input.length > 3000) throw new DebriefError("Use at most 3000 characters.");
  if (!/^[\x09\x0a\x0d\x20-\x7e]*$/.test(input)) throw new DebriefError("Use sample text with ordinary English letters and punctuation.");
  const lines = input.split(/\r?\n/);
  if (lines.filter(line => line.trim()).length > 10) throw new DebriefError("Use at most 10 nonblank sample lines.");
  return lines.flatMap((quote, index) => {
    if (!quote.trim()) return [];
    const match = /^[ \t]*(observation|action|decision|question):[ \t]*(.*)$/i.exec(quote);
    const text = match?.[2].trim();
    if (!match || !text || text.length > 246 || !/^[a-zA-Z0-9 _.-]+$/.test(text)) {
      throw new DebriefError(`Check line ${index + 1}. Use Observation, Action, Decision or Question followed by a colon and 1–246 sample text characters. Use letters, numbers, spaces, dots, underscores or hyphens.`);
    }
    return [Object.freeze({ line: index + 1, kind: kinds[match[1].toLowerCase() as keyof typeof kinds], text, quote })];
  });
}

/** A historical result for another nonce must never label this proposal as saved. */
export function proposalOutcome(request: ProposalRequest | null, nonce: string, state: ProposalState): { line: number; state: ProposalState } | null {
  return request?.request_id === nonce ? { line: request.line, state } : null;
}
