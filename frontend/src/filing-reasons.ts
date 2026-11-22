// Plain-language explanations of a synthetic filing's state and reason (spec 077).
// Honesty rules: waiting is not failed, unknown is not lost, a retry is never a blind second write, and a terminal
// failure after three attempts says so even when the destination was only unreachable. Text only: no server state changes.
const REASONS: Record<string, string> = {
  ambiguous_outcome: "The destination did not confirm whether the filing was written, or cannot be asked right now. Nothing was lost. Butler will ask the destination again and will not write a second time blindly.",
  transient_error: "The destination could not be reached for this attempt. Butler will try again later, up to three attempts in total.",
  reconciled_absent: "The destination confirmed that nothing was written yet. Butler will try once more.",
  attempts_exhausted: "Three attempts did not succeed and nothing was filed. This request is final, even if the destination was only unreachable. Once the destination is back, review the plan and make a new request.",
  collision: "A different file already holds this destination path. Nothing was overwritten. Choose another destination in the plan and make a new request.",
  plan_changed: "The document or its approved plan changed after the request, so the request was cancelled and nothing was filed. Make a new request for the current plan.",
  source_changed: "The document changed or was forgotten, so the request was cancelled and nothing was filed.",
  cancelled_by_owner: "You cancelled this request before it started. Nothing was filed.",
  owner_unavailable: "The owner account was unavailable, so the request was cancelled and nothing was filed.",
  scope_unavailable: "Access to this scope was removed, so the request was cancelled and nothing was filed.",
};
export type FilingLike = { state: string; reason: string | null; attempts: number };
export function filingExplanation(f: FilingLike): string {
  const known = f.reason ? REASONS[f.reason] : undefined;
  if (known) return known;
  switch (f.state) {
    case "pending": return f.attempts === 0 ? "Waiting for the filing worker to start this request. Nothing has been written yet." : "Waiting for the next attempt. Nothing is final yet.";
    case "unknown": return REASONS.ambiguous_outcome;
    case "filed": return "The synthetic destination recorded this filing once.";
    case "failed": return "The filing failed and nothing was filed. Check the document and the plan before making a new request.";
    case "cancelled": return "This request was cancelled and nothing was filed.";
    default: return "";
  }
}
